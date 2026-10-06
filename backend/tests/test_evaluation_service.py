"""Tests for the read-only contract evaluation service."""

from arc.contracts.models import Condition
from arc.core.lifecycle import (
    ContractRuntimeState,
    EvaluationOutcome,
    LifecycleState,
)
from arc.evaluation.service import evaluate_contract
from arc.monitoring.processes import ProcessObservation
from arc.monitoring.system import SystemSnapshot
from tests.conftest import make_contract


def _telemetry(cpu: float = 80.0) -> SystemSnapshot:
    return SystemSnapshot(cpu_percent=cpu, memory_percent=30.0, cpu_count=4, timestamp=0.0)


def _observations() -> list[ProcessObservation]:
    return [
        ProcessObservation(
            pid=50,
            name="python",
            cmdline="python demo_cpu_worker.py",
            cpu_percent=90.0,
            memory_percent=2.0,
        )
    ]


def _runtime(contract_id: str = "compile-relief") -> ContractRuntimeState:
    return ContractRuntimeState(contract_id=contract_id)


def test_disabled_contract_never_activates() -> None:
    """Disabled contracts report disabled without inspecting targets."""
    contract = make_contract(enabled=False)

    result = evaluate_contract(contract, _telemetry(), [], _runtime(), now=0.0)

    assert result.outcome is EvaluationOutcome.DISABLED
    assert result.matched_pids == []


def test_missing_target_is_explicit() -> None:
    """No matching process means target not found, even with high CPU."""
    contract = make_contract(
        trigger={
            "metric": "system.cpu.percent",
            "operator": "gt",
            "value": 75,
            "for_seconds": 0,
        }
    )

    result = evaluate_contract(contract, _telemetry(cpu=99.0), [], _runtime(), now=0.0)

    assert result.outcome is EvaluationOutcome.TARGET_NOT_FOUND
    assert result.trigger_satisfied is False


def test_trigger_pending_before_duration() -> None:
    """A fresh true trigger with for_seconds is pending, not activating."""
    contract = make_contract()
    runtime = _runtime()
    runtime.trigger_tracker.required_seconds = 5

    result = evaluate_contract(contract, _telemetry(), _observations(), runtime, now=100.0)

    assert result.outcome is EvaluationOutcome.TRIGGER_PENDING
    assert result.trigger_raw is True
    assert result.trigger_satisfied is False
    assert result.matched_pids == [50]


def test_trigger_would_activate_after_duration() -> None:
    """A held trigger becomes a preview activation, lifecycle stays put."""
    contract = make_contract()
    runtime = _runtime()
    runtime.trigger_tracker.required_seconds = 5

    evaluate_contract(contract, _telemetry(), _observations(), runtime, now=100.0)
    result = evaluate_contract(contract, _telemetry(), _observations(), runtime, now=105.0)

    assert result.outcome is EvaluationOutcome.WOULD_ACTIVATE
    assert result.trigger_satisfied is True
    assert runtime.lifecycle is LifecycleState.INACTIVE


def test_immediate_trigger_would_activate() -> None:
    """for_seconds=0 activates the preview on the first true sample."""
    contract = make_contract(
        trigger={"metric": "system.cpu.percent", "operator": "gt", "value": 75}
    )
    runtime = _runtime()

    result = evaluate_contract(contract, _telemetry(), _observations(), runtime, now=0.0)

    assert result.outcome is EvaluationOutcome.WOULD_ACTIVATE


def test_false_trigger_stays_pending() -> None:
    """A false comparison never previews activation."""
    contract = make_contract(
        trigger={"metric": "system.cpu.percent", "operator": "gt", "value": 75}
    )

    result = evaluate_contract(contract, _telemetry(cpu=10.0), _observations(), _runtime(), now=0.0)

    assert result.outcome is EvaluationOutcome.TRIGGER_PENDING
    assert result.trigger_raw is False


def test_evaluation_error_is_surfaced() -> None:
    """Unevaluable conditions produce errors, not crashes or activation."""
    contract = make_contract()
    contract.trigger = Condition.model_construct(  # type: ignore[assignment]
        metric="not.a.metric", operator="gt", value=1, for_seconds=0
    )
    runtime = _runtime()

    result = evaluate_contract(contract, _telemetry(), _observations(), runtime, now=0.0)

    assert result.outcome is EvaluationOutcome.EVALUATION_ERROR
    assert result.error is not None
    assert runtime.lifecycle is LifecycleState.ERROR
