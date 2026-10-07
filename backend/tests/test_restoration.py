"""Tests for restoration: exact values, identity safety, exit handling."""

from arc.core.lifecycle import EvaluationOutcome, LifecycleState
from arc.linux.fake_adapter import FakeProcess
from arc.linux.resources import ResourceSnapshot
from arc.restoration.service import restore_snapshots
from tests.conftest import make_engine, make_fake, make_observation, make_telemetry


def _snapshots(fake, *pids: int) -> list[ResourceSnapshot]:
    return [
        ResourceSnapshot(
            identity=fake.get_identity(pid),
            nice=fake.get_nice(pid),
            affinity=fake.get_affinity(pid),
        )
        for pid in pids
    ]


def test_restore_exact_nice_and_affinity() -> None:
    """Restoration writes back recorded values, verified."""
    fake = make_fake(pid=50, nice=5, affinity=(0, 1, 2, 3))
    snapshots = _snapshots(fake, 50)
    fake.set_nice(50, 10)
    fake.set_affinity(50, [0])

    result = restore_snapshots(snapshots, fake)

    assert result.ok is True
    assert result.restored == [50]
    assert fake.get_nice(50) == 5
    assert fake.get_affinity(50) == (0, 1, 2, 3)


def test_restore_multiple_targets() -> None:
    """Every snapshot restores independently."""
    fake = make_fake(pid=50, nice=5)
    fake.add_process(FakeProcess(pid=60, create_time=2000.0, nice=7, affinity=(0, 1)))
    snapshots = _snapshots(fake, 50, 60)
    fake.set_nice(50, 10)
    fake.set_nice(60, 10)

    result = restore_snapshots(snapshots, fake)

    assert result.ok is True
    assert result.restored == [50, 60]
    assert fake.get_nice(50) == 5
    assert fake.get_nice(60) == 7


def test_exited_target_needs_no_restoration() -> None:
    """A gone process is recorded, not an error."""
    fake = make_fake(pid=50, nice=5)
    snapshots = _snapshots(fake, 50)
    fake.remove_process(50)

    result = restore_snapshots(snapshots, fake)

    assert result.ok is True
    assert result.disappeared == [50]
    assert result.restored == []


def test_reused_pid_is_never_touched() -> None:
    """Same PID with a new creation time is stale: hands off."""
    fake = make_fake(pid=50, nice=5, create_time=1000.0)
    snapshots = _snapshots(fake, 50)
    new = fake.replace_process(50, create_time=2000.0)
    new.nice = 0

    result = restore_snapshots(snapshots, fake)

    assert result.ok is False
    assert result.stale == [50]
    assert fake.get_nice(50) == 0


def test_failed_restore_is_reported() -> None:
    """Denied writes surface as failed entries."""
    fake = make_fake(pid=50, nice=5)
    snapshots = _snapshots(fake, 50)
    fake.set_nice(50, 10)
    fake.deny_on("set_nice", 50)

    result = restore_snapshots(snapshots, fake)

    assert result.ok is False
    assert result.failed == [50]


def test_engine_restores_exact_values_and_clears_state() -> None:
    """Full engine path: ACTIVE, restore satisfied, INACTIVE, timers reset."""
    engine, fake = make_engine()
    assert fake.get_nice(50) == 0
    engine.step(make_telemetry(cpu=80.0), [make_observation()], now=0.0)
    engine.step(make_telemetry(cpu=80.0), [make_observation()], now=5.0)
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.ACTIVE

    engine.step(make_telemetry(cpu=10.0), [make_observation()], now=10.0)
    done = engine.step(make_telemetry(cpu=10.0), [make_observation()], now=15.0)

    assert done.evaluations[0].outcome is EvaluationOutcome.RESTORED
    assert fake.get_nice(50) == 0
    runtime = engine.runtime_for("compile-relief")
    assert runtime is not None
    assert runtime.lifecycle is LifecycleState.INACTIVE
    assert runtime.snapshots == []
    assert runtime.activated_at is None


def test_engine_reuses_pid_safely() -> None:
    """PID reuse during ACTIVE becomes RESTORATION_ERROR, new proc intact."""
    engine, fake = make_engine()
    engine.step(make_telemetry(cpu=80.0), [make_observation()], now=0.0)
    engine.step(make_telemetry(cpu=80.0), [make_observation()], now=5.0)
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.ACTIVE

    reused = fake.replace_process(50, create_time=9999.0)
    reused.nice = 3
    result = engine.step(make_telemetry(cpu=10.0), [make_observation()], now=10.0)

    assert result.evaluations[0].outcome is EvaluationOutcome.RESTORATION_ERROR
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.ERROR
    assert fake.get_nice(50) == 3


def test_engine_retires_when_all_targets_exit() -> None:
    """No live snapshots left: retire to INACTIVE instead of hanging."""
    engine, fake = make_engine()
    engine.step(make_telemetry(cpu=80.0), [make_observation()], now=0.0)
    engine.step(make_telemetry(cpu=80.0), [make_observation()], now=5.0)
    fake.remove_process(50)

    result = engine.step(make_telemetry(cpu=80.0), [make_observation()], now=10.0)

    assert result.evaluations[0].outcome is EvaluationOutcome.RESTORED
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.INACTIVE


def test_engine_partial_exit_restores_survivors() -> None:
    """One exit plus one survivor: survivor restores, episode completes."""
    from tests.conftest import make_contract

    fake = make_fake(pid=50, nice=5)
    fake.add_process(FakeProcess(pid=60, create_time=2000.0, nice=7, affinity=(0, 1)))
    engine, _ = make_engine([make_contract()], adapter=fake)
    both = [make_observation(pid=50), make_observation(pid=60)]
    engine.step(make_telemetry(cpu=80.0), both, now=0.0)
    engine.step(make_telemetry(cpu=80.0), both, now=5.0)
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.ACTIVE

    fake.remove_process(60)
    engine.step(make_telemetry(cpu=10.0), both, now=10.0)
    done = engine.step(make_telemetry(cpu=10.0), both, now=15.0)

    assert done.evaluations[0].outcome is EvaluationOutcome.RESTORED
    assert fake.get_nice(50) == 5
    assert engine.runtime_for("compile-relief").lifecycle is LifecycleState.INACTIVE
