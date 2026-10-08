"""Tests for cgroups v2 integration and FakeCgroupManager."""

from arc.enforcement.service import activate_contract
from arc.linux.cgroups import FakeCgroupManager, LinuxCgroupManager
from arc.linux.fake_adapter import FakeProcess, FakeResourceAdapter
from arc.linux.resources import ResourcePermissionError
from arc.restoration.service import restore_snapshots
from tests.conftest import make_contract, make_observation


def test_fake_cgroup_manager_quota_flow() -> None:
    fake_adapter = FakeResourceAdapter()
    fake_adapter.add_process(FakeProcess(pid=50, create_time=1000.0))
    cgroup_mgr = FakeCgroupManager()

    contract = make_contract(actions=[{"type": "cpu_quota", "quota_percent": 50.0}])
    targets = [make_observation(pid=50)]

    result = activate_contract(contract, targets, fake_adapter, cgroup_manager=cgroup_mgr)
    assert result.ok is True
    assert 50 in cgroup_mgr._quotas
    assert cgroup_mgr.get_quota(50) == "50000 100000"

    # Restore
    restore_res = restore_snapshots(result.snapshots, fake_adapter, cgroup_manager=cgroup_mgr)
    assert restore_res.ok is True
    assert 50 not in cgroup_mgr._quotas


def test_linux_cgroup_capabilities_honest() -> None:
    mgr = LinuxCgroupManager()
    caps = mgr.capabilities()
    # On Windows or non-cgroup systems, available is False with honest reason
    assert isinstance(caps.available, bool)
    assert isinstance(caps.reason, str)


def test_snapshot_failure_cleans_up_earlier_cgroup_leases() -> None:
    class FailSecondEnter(FakeCgroupManager):
        def enter(self, pid: int):
            if pid == 60:
                raise ResourcePermissionError("cgroup_enter", pid, "injected second failure")
            return super().enter(pid)

    fake_adapter = FakeResourceAdapter()
    fake_adapter.add_process(FakeProcess(pid=50, create_time=1000.0))
    fake_adapter.add_process(FakeProcess(pid=60, create_time=1000.0))
    cgroup_mgr = FailSecondEnter()
    contract = make_contract(actions=[{"type": "cpu_quota", "quota_percent": 50.0}])

    result = activate_contract(
        contract,
        [make_observation(pid=50), make_observation(pid=60)],
        fake_adapter,
        cgroup_manager=cgroup_mgr,
    )

    assert result.ok is False
    assert result.failure is not None
    assert result.failure.rolled_back is True
    assert cgroup_mgr._quotas == {}
