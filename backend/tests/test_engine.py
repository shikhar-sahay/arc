"""Tests for the persistent runtime engine (fake adapter, no OS changes)."""

import pytest

from arc.core.engine import ObservationEngine
from arc.core.lifecycle import EvaluationOutcome, LifecycleState
from arc.monitoring.processes import ProcessObservation
from tests.conftest import (
    DenyingAdapter,
    make_contract,
    make_engine,
    make_fake,
    make_observation,
    make_telemetry,
)


def _obs(pid: int = 50) -> list[ProcessObservation]:
    return [make_observation(pid=pid)]


def test_engine_rejects_non_positive_interval() -> None:
    """Polling intervals must be positive."""
    with pytest.raises(ValueError):
        ObservationEngine([], poll_interval_seconds=0)


def test_full_lifecycle_activate_then_restore() -> None:
    """Trigger satisfied, enforced, restore satisfied, exact state back."""
    engine, fake = make_engine()
    assert fake.get_nice(50) == 0

    pending = engine.step(make_telemetry(cpu=80.0), _obs(), now=0.0)
    assert pending.evaluations[0].outcome is EvaluationOutcome.TRIGGER_PENDING

    activated = engine.step(make_telemetry(cpu=80.0), _obs(), now=5.0)
    assert activated.evaluations[0].outcome is EvaluationOutcome.ACTIVATED
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.ACTIVE
    assert fake.get_nice(50) == 10

    still = engine.step(make_telemetry(cpu=80.0), _obs(), now=10.0)
    assert still.evaluations[0].outcome is EvaluationOutcome.STILL_ACTIVE

    engine.step(make_telemetry(cpu=10.0), _obs(), now=15.0)
    restored = engine.step(make_telemetry(cpu=10.0), _obs(), now=20.0)
    assert restored.evaluations[0].outcome is EvaluationOutcome.RESTORED
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.INACTIVE
    assert fake.get_nice(50) == 0

    runtime = engine.runtime_for("compile-relief")
    assert runtime is not None
    assert runtime.snapshots == []
    assert runtime.activated_at is None


def test_trigger_timer_resets_after_restore() -> None:
    """A new episode needs the full trigger duration again."""
    engine, _ = make_engine()
    engine.step(make_telemetry(cpu=80.0), _obs(), now=0.0)
    engine.step(make_telemetry(cpu=80.0), _obs(), now=5.0)
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.ACTIVE
    engine.step(make_telemetry(cpu=10.0), _obs(), now=10.0)
    engine.step(make_telemetry(cpu=10.0), _obs(), now=15.0)
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.INACTIVE

    pending = engine.step(make_telemetry(cpu=80.0), _obs(), now=16.0)
    assert pending.evaluations[0].outcome is EvaluationOutcome.TRIGGER_PENDING
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.INACTIVE


def test_snapshot_evaluation_resets_when_target_vanishes() -> None:
    """A disappearing target clears progress instead of activating."""
    engine, _ = make_engine()

    engine.step(make_telemetry(), _obs(), now=0.0)
    gone = engine.step(make_telemetry(), [], now=10.0)

    assert gone.evaluations[0].outcome is EvaluationOutcome.TARGET_NOT_FOUND


def test_error_contract_is_not_retried() -> None:
    """ERROR latches: further steps make no adapter calls."""
    engine, fake = make_engine()
    fake.fail_on("set_nice", 50)

    engine.step(make_telemetry(), _obs(), now=0.0)
    failed = engine.step(make_telemetry(), _obs(), now=5.0)
    assert failed.evaluations[0].outcome is EvaluationOutcome.ACTIVATION_ERROR
    calls_after_failure = len(fake.calls)

    again = engine.step(make_telemetry(), _obs(), now=10.0)
    assert again.evaluations[0].outcome is EvaluationOutcome.ACTIVATION_ERROR
    assert len(fake.calls) == calls_after_failure
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.ERROR


def test_disabled_contract_never_enforces() -> None:
    """Disabled contracts stay silent and untouched."""
    engine, fake = make_engine([make_contract(enabled=False)])

    result = engine.step(make_telemetry(), _obs(), now=0.0)

    assert result.evaluations[0].outcome is EvaluationOutcome.DISABLED
    assert fake.calls == []


def test_unsupported_action_fails_without_mutation() -> None:
    """An unsupported action type fails: explicit failure, zero resource writes."""
    contract = make_contract()

    class BogusAction:
        type = "bogus_unsupported_action"

    contract.actions.append(BogusAction())  # type: ignore[arg-type]
    engine, fake = make_engine([contract])

    engine.step(make_telemetry(), _obs(), now=0.0)
    result = engine.step(make_telemetry(), _obs(), now=5.0)

    assert result.evaluations[0].outcome is EvaluationOutcome.ACTIVATION_ERROR
    assert "bogus_unsupported_action" in (result.evaluations[0].error or "")
    assert fake.calls == []
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.ERROR


def test_unsupported_platform_stays_preview() -> None:
    """Without enforcement support, satisfied triggers only preview."""
    engine = ObservationEngine(
        [make_contract()],
        resource_adapter=DenyingAdapter(),
    )

    first = engine.step(make_telemetry(), _obs(), now=0.0)
    second = engine.step(make_telemetry(), _obs(), now=5.0)

    assert first.evaluations[0].outcome is EvaluationOutcome.TRIGGER_PENDING
    assert second.evaluations[0].outcome is EvaluationOutcome.WOULD_ACTIVATE
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.INACTIVE


def test_runtime_state_stays_out_of_configuration() -> None:
    """Evaluation records runtime state without touching the contract."""
    contract = make_contract()
    engine, _ = make_engine([contract])
    before = contract.model_dump()

    engine.step(make_telemetry(), _obs(), now=0.0)
    runtime = engine.runtime_for(contract.id)

    assert contract.model_dump() == before
    assert runtime is not None
    assert runtime.matched_pids == [50]


def test_graceful_shutdown_restores_active() -> None:
    """Shutdown best-effort restores ACTIVE contracts before exit."""
    engine, fake = make_engine()
    engine.step(make_telemetry(), _obs(), now=0.0)
    engine.step(make_telemetry(), _obs(), now=5.0)
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.ACTIVE
    assert fake.get_nice(50) == 10

    problems = engine.shutdown()

    assert problems == []
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.INACTIVE
    assert fake.get_nice(50) == 0


def test_manual_reset_recovers_error() -> None:
    """An errored contract can be reset to INACTIVE explicitly."""
    engine, fake = make_engine()
    fake.fail_on("set_nice", 50)
    engine.step(make_telemetry(), _obs(), now=0.0)
    engine.step(make_telemetry(), _obs(), now=5.0)
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.ERROR

    assert engine.reset_contract("compile-relief") is True
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.INACTIVE
    assert engine.reset_contract("compile-relief") is False


def test_seeded_fake_reports_configured_nice() -> None:
    """Sanity check on the shared fake seed helper."""
    fake = make_fake(pid=51, nice=5)
    assert fake.get_nice(51) == 5
