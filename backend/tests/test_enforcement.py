"""Tests for activation: snapshots, ordering, rollback (fake adapter)."""

from arc.enforcement.service import SUPPORTED_ACTION_TYPES, activate_contract
from arc.linux.fake_adapter import FakeProcess, FakeResourceAdapter
from tests.conftest import DenyingAdapter, make_contract, make_fake, make_observation


def _targets(*pids: int):
    return [make_observation(pid=pid) for pid in pids]


def _seed(fake: FakeResourceAdapter, *pids: int) -> None:
    for pid in pids:
        fake.add_process(FakeProcess(pid=pid, create_time=1000.0, nice=0, affinity=(0, 1, 2, 3)))


def test_supported_action_types() -> None:
    """Only nice and cpu_affinity execute in this pass."""
    assert SUPPORTED_ACTION_TYPES == ("nice", "cpu_affinity")


def test_successful_nice_activation() -> None:
    """Nice is captured, applied, and verified."""
    fake = make_fake(pid=50, nice=5)
    contract = make_contract(actions=[{"type": "nice", "value": 10}])

    result = activate_contract(contract, _targets(50), fake)

    assert result.ok is True
    assert result.snapshots[0].nice == 5
    assert result.snapshots[0].identity.pid == 50
    assert result.snapshots[0].identity.create_time == 1000.0
    assert fake.get_nice(50) == 10


def test_affinity_only_captures_affinity() -> None:
    """Affinity contracts snapshot affinity, not nice."""
    fake = make_fake(pid=50, nice=3, affinity=(0, 1, 2, 3))
    contract = make_contract(actions=[{"type": "cpu_affinity", "cpus": [0, 1]}])

    result = activate_contract(contract, _targets(50), fake)

    assert result.ok is True
    assert result.snapshots[0].nice is None
    assert result.snapshots[0].affinity == (0, 1, 2, 3)
    assert fake.get_affinity(50) == (0, 1)


def test_multiple_actions_follow_contract_order() -> None:
    """Actions apply in contract order, verified through call order."""
    fake = make_fake(pid=50)
    contract = make_contract(
        actions=[{"type": "nice", "value": 10}, {"type": "cpu_affinity", "cpus": [0]}]
    )

    result = activate_contract(contract, _targets(50), fake)

    assert result.ok is True
    kinds = [call[0] for call in fake.calls]
    assert kinds == ["set_nice", "set_affinity"]
    assert result.snapshots[0].nice == 0
    assert result.snapshots[0].affinity == (0, 1, 2, 3)


def test_multiple_targets_each_get_snapshot_in_pid_order() -> None:
    """Every target is enforced, none is silently skipped."""
    fake = FakeResourceAdapter()
    _seed(fake, 60, 50)
    contract = make_contract(actions=[{"type": "nice", "value": 10}])

    result = activate_contract(contract, _targets(60, 50), fake)

    assert result.ok is True
    assert [snap.identity.pid for snap in result.snapshots] == [50, 60]
    assert fake.get_nice(50) == 10
    assert fake.get_nice(60) == 10
    assert [call[1] for call in fake.calls] == [50, 60]


def test_first_action_failure_leaves_nothing_applied() -> None:
    """A snapshot-time failure means zero mutations to roll back."""
    fake = make_fake(pid=50)
    fake.fail_on("set_nice", 50)
    contract = make_contract(actions=[{"type": "nice", "value": 10}])

    result = activate_contract(contract, _targets(50), fake)

    assert result.ok is False
    assert result.failure is not None
    assert result.failure.rolled_back is True
    assert fake.get_nice(50) == 0


def test_late_failure_rolls_back_earlier_mutation() -> None:
    """Nice applied then affinity fails: nice must return to 0."""
    fake = make_fake(pid=50, nice=0)
    fake.fail_on("set_affinity", 50)
    contract = make_contract(
        actions=[{"type": "nice", "value": 10}, {"type": "cpu_affinity", "cpus": [0]}]
    )

    result = activate_contract(contract, _targets(50), fake)

    assert result.ok is False
    assert result.failure is not None
    assert result.failure.rolled_back is True
    assert fake.get_nice(50) == 0


def test_rollback_failure_is_surfaced() -> None:
    """A process exiting mid-activation breaks rollback explicitly."""
    fake = make_fake(pid=50, nice=0)
    fake.fail_on("set_affinity", 50)
    contract = make_contract(
        actions=[{"type": "nice", "value": 10}, {"type": "cpu_affinity", "cpus": [0]}]
    )
    from arc.enforcement import service as enforcement_service

    real_set_nice = fake.set_nice
    calls = {"count": 0}

    def flaky_set_nice(pid: int, value: int) -> None:
        calls["count"] += 1
        if calls["count"] > 1:
            fake.remove_process(pid)
        return real_set_nice(pid, value)

    fake.set_nice = flaky_set_nice  # type: ignore[method-assign]
    try:
        result = enforcement_service.activate_contract(contract, _targets(50), fake)
    finally:
        fake.set_nice = real_set_nice  # type: ignore[method-assign]

    assert result.ok is False
    assert result.failure is not None
    assert result.failure.rolled_back is False
    assert result.failure.rollback_errors != []


def test_unsupported_action_applies_nothing() -> None:
    """Suspend/resume fail closed before any snapshot or mutation."""
    fake = make_fake(pid=50)
    contract = make_contract(actions=[{"type": "suspend"}])

    result = activate_contract(contract, _targets(50), fake)

    assert result.ok is False
    assert "suspend" in (result.failure.error if result.failure else "")
    assert result.snapshots == []
    assert fake.calls == []


def test_unsupported_platform_fails_cleanly() -> None:
    """A refusing adapter yields failure, never fake success."""
    contract = make_contract()

    result = activate_contract(contract, _targets(50), DenyingAdapter())

    assert result.ok is False
