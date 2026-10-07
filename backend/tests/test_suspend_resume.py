"""Tests for suspend and resume actions and restoration semantics."""

from arc.enforcement.service import activate_contract
from arc.linux.fake_adapter import FakeProcess, FakeResourceAdapter
from arc.restoration.service import restore_snapshots
from tests.conftest import make_contract, make_observation


def _targets(*pids: int):
    return [make_observation(pid=pid) for pid in pids]


def test_suspend_running_process() -> None:
    fake = FakeResourceAdapter()
    fake.add_process(FakeProcess(pid=50, create_time=1000.0, stopped=False))
    contract = make_contract(actions=[{"type": "suspend"}])

    result = activate_contract(contract, _targets(50), fake)
    assert result.ok is True
    assert fake.is_stopped(50) is True
    assert result.snapshots[0].stopped is False

    # Restoration should resume the process because snapshot.stopped was False
    restore_res = restore_snapshots(result.snapshots, fake)
    assert restore_res.ok is True
    assert fake.is_stopped(50) is False


def test_suspend_already_stopped_process() -> None:
    fake = FakeResourceAdapter()
    fake.add_process(FakeProcess(pid=50, create_time=1000.0, stopped=True))
    contract = make_contract(actions=[{"type": "suspend"}])

    result = activate_contract(contract, _targets(50), fake)
    assert result.ok is True
    assert fake.is_stopped(50) is True
    assert result.snapshots[0].stopped is True

    # Restoration should NOT resume a process that was originally stopped
    restore_res = restore_snapshots(result.snapshots, fake)
    assert restore_res.ok is True
    assert fake.is_stopped(50) is True


def test_resume_stopped_process() -> None:
    fake = FakeResourceAdapter()
    fake.add_process(FakeProcess(pid=50, create_time=1000.0, stopped=True))
    contract = make_contract(actions=[{"type": "resume"}])

    result = activate_contract(contract, _targets(50), fake)
    assert result.ok is True
    assert fake.is_stopped(50) is False
    assert result.snapshots[0].stopped is True

    # Restoration should suspend it back because snapshot.stopped was True
    restore_res = restore_snapshots(result.snapshots, fake)
    assert restore_res.ok is True
    assert fake.is_stopped(50) is True


def test_self_protection_against_suspending_engine() -> None:
    fake = FakeResourceAdapter(engine_pid=100)
    fake.add_process(FakeProcess(pid=100, create_time=1000.0, stopped=False))
    contract = make_contract(actions=[{"type": "suspend"}])

    result = activate_contract(contract, _targets(100), fake)
    assert result.ok is False
    assert "refusing to suspend ARC's own runtime process" in (
        result.failure.error if result.failure else ""
    )
    assert fake.is_stopped(100) is False
