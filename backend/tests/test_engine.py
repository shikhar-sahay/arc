"""Tests for the read-only observation engine."""

import pytest

from arc.core.engine import ObservationEngine
from arc.core.lifecycle import EvaluationOutcome
from arc.monitoring.processes import ProcessObservation
from arc.monitoring.system import SystemSnapshot
from tests.conftest import make_contract


def _telemetry(cpu: float = 80.0) -> SystemSnapshot:
    return SystemSnapshot(cpu_percent=cpu, memory_percent=30.0, cpu_count=4, timestamp=0.0)


def _observations() -> list[ProcessObservation]:
    return [
        ProcessObservation(
            pid=7,
            name="python",
            cmdline="python demo_cpu_worker.py",
            cpu_percent=90.0,
            memory_percent=2.0,
        )
    ]


def test_engine_rejects_non_positive_interval() -> None:
    """Polling intervals must be positive."""
    with pytest.raises(ValueError):
        ObservationEngine([], poll_interval_seconds=0)


def test_snapshot_evaluation_tracks_duration_without_sleeping() -> None:
    """Injected snapshots and times drive pending then would-activate."""
    engine = ObservationEngine([make_contract()])

    first = engine.evaluate_snapshot(_telemetry(), _observations(), now=1000.0)
    second = engine.evaluate_snapshot(_telemetry(), _observations(), now=1005.0)

    assert first[0].outcome is EvaluationOutcome.TRIGGER_PENDING
    assert second[0].outcome is EvaluationOutcome.WOULD_ACTIVATE


def test_snapshot_evaluation_resets_when_target_vanishes() -> None:
    """A disappearing target clears progress instead of activating."""
    engine = ObservationEngine([make_contract()])

    engine.evaluate_snapshot(_telemetry(), _observations(), now=0.0)
    gone = engine.evaluate_snapshot(_telemetry(), [], now=10.0)
    back = engine.evaluate_snapshot(_telemetry(), _observations(), now=11.0)

    assert gone[0].outcome is EvaluationOutcome.TARGET_NOT_FOUND
    assert back[0].outcome is EvaluationOutcome.TRIGGER_PENDING


def test_runtime_state_stays_out_of_configuration() -> None:
    """Evaluation records runtime state without touching the contract."""
    contract = make_contract()
    engine = ObservationEngine([contract])
    before = contract.model_dump()

    engine.evaluate_snapshot(_telemetry(), _observations(), now=0.0)
    runtime = engine.runtime_for(contract.id)

    assert contract.model_dump() == before
    assert runtime is not None
    assert runtime.matched_pids == [7]
    assert runtime.last_outcome is EvaluationOutcome.TRIGGER_PENDING


def test_poll_uses_injected_samplers() -> None:
    """Live polling reads through the configured monitor and sampler."""
    engine = ObservationEngine(
        [make_contract()],
        process_sampler=_observations,
    )

    cycle = engine.poll()

    assert cycle.process_count == 1
    assert len(cycle.evaluations) == 1
    assert cycle.telemetry.cpu_count >= 1
