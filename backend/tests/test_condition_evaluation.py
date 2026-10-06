"""Tests for condition evaluation and duration handling.

All time is injected as monotonic seconds. No test sleeps.
"""

import pytest

from arc.contracts.models import Condition
from arc.core.lifecycle import DurationTracker
from arc.evaluation.service import ConditionEvaluationError, evaluate_condition
from arc.monitoring.processes import ProcessObservation
from arc.monitoring.system import SystemSnapshot


def _telemetry(cpu: float = 80.0, memory: float = 40.0) -> SystemSnapshot:
    return SystemSnapshot(cpu_percent=cpu, memory_percent=memory, cpu_count=4, timestamp=0.0)


def _matched() -> list[ProcessObservation]:
    return [
        ProcessObservation(
            pid=10,
            name="python",
            cmdline="python work.py",
            cpu_percent=5.0,
            memory_percent=1.0,
        )
    ]


def _condition(metric: str, operator: str, value: object, for_seconds: float = 0) -> Condition:
    return Condition.model_validate(
        {"metric": metric, "operator": operator, "value": value, "for_seconds": for_seconds}
    )


@pytest.mark.parametrize(
    ("operator", "cpu", "expected"),
    [
        ("gt", 80.0, True),
        ("gt", 75.0, False),
        ("gte", 75.0, True),
        ("lt", 70.0, True),
        ("lt", 75.0, False),
        ("lte", 75.0, True),
        ("eq", 75.0, True),
        ("eq", 75.1, False),
        ("ne", 75.1, True),
        ("ne", 75.0, False),
    ],
)
def test_numeric_operators(operator: str, cpu: float, expected: bool) -> None:
    """Each numeric operator compares the telemetry value correctly."""
    result = evaluate_condition(
        _condition("system.cpu.percent", operator, 75),
        _telemetry(cpu=cpu),
        _matched(),
        DurationTracker(),
        now=100.0,
    )

    assert result.raw is expected
    assert result.satisfied is expected


def test_memory_metric_reads_memory_value() -> None:
    """Memory conditions use memory percent, not CPU percent."""
    result = evaluate_condition(
        _condition("system.memory.percent", "gt", 50),
        _telemetry(cpu=99.0, memory=40.0),
        _matched(),
        DurationTracker(),
        now=0.0,
    )

    assert result.raw is False


@pytest.mark.parametrize(
    ("operator", "value", "matched_count", "expected"),
    [
        ("eq", True, 1, True),
        ("eq", True, 0, False),
        ("eq", False, 0, True),
        ("ne", True, 0, True),
        ("ne", False, 1, True),
    ],
)
def test_presence_conditions(
    operator: str, value: bool, matched_count: int, expected: bool
) -> None:
    """Presence conditions compare target existence as a boolean."""
    matched = _matched()[:matched_count]
    result = evaluate_condition(
        _condition("target.process.present", operator, value),
        _telemetry(),
        matched,
        DurationTracker(),
        now=0.0,
    )

    assert result.raw is expected
    assert result.satisfied is expected


def test_immediate_satisfaction_without_duration() -> None:
    """for_seconds=0 satisfies as soon as the comparison is true."""
    result = evaluate_condition(
        _condition("system.cpu.percent", "gt", 75),
        _telemetry(cpu=80.0),
        _matched(),
        DurationTracker(),
        now=42.0,
    )

    assert result.raw is True
    assert result.satisfied is True
    assert result.elapsed_seconds == 0.0


def test_duration_pending_then_satisfied() -> None:
    """A held condition flips from pending to satisfied over time."""
    tracker = DurationTracker(required_seconds=5)
    condition = _condition("system.cpu.percent", "gt", 75, for_seconds=5)

    first = evaluate_condition(condition, _telemetry(cpu=80.0), _matched(), tracker, now=1000.0)
    middle = evaluate_condition(condition, _telemetry(cpu=80.0), _matched(), tracker, now=1002.0)
    done = evaluate_condition(condition, _telemetry(cpu=80.0), _matched(), tracker, now=1005.0)

    assert (first.raw, first.satisfied) == (True, False)
    assert (middle.raw, middle.satisfied) == (True, False)
    assert middle.elapsed_seconds == pytest.approx(2.0)
    assert (done.raw, done.satisfied) == (True, True)


def test_duration_resets_after_false_sample() -> None:
    """One false sample discards partial duration progress."""
    tracker = DurationTracker(required_seconds=5)
    condition = _condition("system.cpu.percent", "gt", 75, for_seconds=5)

    evaluate_condition(condition, _telemetry(cpu=80.0), _matched(), tracker, now=0.0)
    evaluate_condition(condition, _telemetry(cpu=10.0), _matched(), tracker, now=4.0)
    restarted = evaluate_condition(condition, _telemetry(cpu=80.0), _matched(), tracker, now=8.0)

    assert restarted.raw is True
    assert restarted.satisfied is False
    assert restarted.elapsed_seconds == pytest.approx(0.0)


def test_negative_required_duration_rejected() -> None:
    """Duration trackers refuse negative requirements."""
    with pytest.raises(ValueError):
        DurationTracker(required_seconds=-1)


def test_unsupported_metric_raises() -> None:
    """Defensive path for metrics outside the validated enum."""
    condition = Condition.model_construct(
        metric="not.a.metric", operator="gt", value=1, for_seconds=0
    )

    with pytest.raises(ConditionEvaluationError):
        evaluate_condition(condition, _telemetry(), _matched(), DurationTracker(), now=0.0)
