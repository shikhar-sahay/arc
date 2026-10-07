"""Tests for the event history: transitions, no spam, bounds."""

from arc.core.lifecycle import EvaluationOutcome
from arc.observability.events import ArcEventType, EventLog
from tests.conftest import make_engine, make_observation, make_telemetry


def test_event_log_sequences_and_orders_newest_first() -> None:
    """Events carry increasing seq ids and read back newest first."""
    log = EventLog()
    log.record(ArcEventType.ENGINE_STARTED, "started")
    log.record(ArcEventType.CONTRACT_ACTIVATED, "active", contract_id="c", pid=50)

    recent = log.recent(10)

    assert [event.seq for event in recent] == [2, 1]
    assert recent[0].type is ArcEventType.CONTRACT_ACTIVATED
    assert recent[0].contract_id == "c"
    assert recent[0].pid == 50


def test_event_log_rejects_bad_limit() -> None:
    """Non-positive limits are rejected."""
    log = EventLog()

    try:
        log.recent(0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_event_log_is_bounded() -> None:
    """History keeps only the newest entries."""
    log = EventLog(maxlen=3)
    for index in range(5):
        log.record(ArcEventType.ENGINE_STARTED, f"event {index}")

    assert len(log) == 3
    assert [event.message for event in log.recent(10)] == ["event 4", "event 3", "event 2"]


def test_engine_emits_lifecycle_transitions() -> None:
    """A full episode leaves an audit trail of transitions."""
    engine, _ = make_engine()
    engine.start()
    engine.step(make_telemetry(cpu=80.0), [make_observation()], now=0.0)
    engine.step(make_telemetry(cpu=80.0), [make_observation()], now=5.0)
    engine.step(make_telemetry(cpu=10.0), [make_observation()], now=10.0)
    engine.step(make_telemetry(cpu=10.0), [make_observation()], now=15.0)

    types = [event.type for event in engine.recent_events(500)]

    for expected in (
        ArcEventType.ENGINE_STARTED,
        ArcEventType.CONTRACT_TRIGGER_PENDING,
        ArcEventType.CONTRACT_ACTIVATING,
        ArcEventType.RESOURCE_SNAPSHOT_CAPTURED,
        ArcEventType.RESOURCE_ACTION_APPLIED,
        ArcEventType.CONTRACT_ACTIVATED,
        ArcEventType.RESTORE_PENDING,
        ArcEventType.CONTRACT_RESTORING,
        ArcEventType.RESOURCE_RESTORED,
        ArcEventType.CONTRACT_RESTORED,
    ):
        assert expected in types


def test_repeated_pending_steps_emit_once() -> None:
    """Identical outcomes do not spam the history every poll."""
    engine, _ = make_engine()
    for now in (0.0, 1.0, 2.0, 3.0):
        engine.step(make_telemetry(cpu=10.0), [make_observation()], now=now)

    pending = [
        event
        for event in engine.recent_events(500)
        if event.type is ArcEventType.CONTRACT_TRIGGER_PENDING
    ]

    assert len(pending) == 1


def test_error_paths_emit_failure_events() -> None:
    """Activation failure records enforcement and rollback events."""
    engine, fake = make_engine()
    fake.fail_on("set_nice", 50)
    engine.step(make_telemetry(), [make_observation()], now=0.0)
    engine.step(make_telemetry(), [make_observation()], now=5.0)

    types = [event.type for event in engine.recent_events(500)]

    assert ArcEventType.ENFORCEMENT_FAILED in types
    assert ArcEventType.ROLLBACK_COMPLETED in types


def test_last_outcome_tracks_transitions() -> None:
    """Runtime outcomes follow the episode for API readers."""
    engine, _ = make_engine()
    engine.step(make_telemetry(cpu=80.0), [make_observation()], now=0.0)
    runtime = engine.runtime_for("compile-relief")
    assert runtime is not None
    assert runtime.last_outcome is EvaluationOutcome.TRIGGER_PENDING
