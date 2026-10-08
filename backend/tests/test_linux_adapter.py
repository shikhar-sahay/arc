"""Tests for the Linux boundary: refusal off Linux, fake behavior, mapping."""

import sys

import psutil
import pytest

from arc.linux.capabilities import detect_capabilities
from arc.linux.fake_adapter import FakeProcess
from arc.linux.psutil_adapter import LinuxResourceAdapter
from arc.linux.resources import (
    ProcessNotFoundError,
    ResourceControlError,
    ResourcePermissionError,
    UnsupportedPlatformError,
)
from tests.conftest import make_fake

LINUX_ONLY = pytest.mark.skipif(sys.platform != "linux", reason="requires Linux")


def test_real_adapter_refuses_off_linux() -> None:
    """Off Linux every operation fails clearly instead of faking success."""
    adapter = LinuxResourceAdapter()
    if sys.platform == "linux":
        pytest.skip("only meaningful off Linux")

    assert adapter.enforcement_supported is False
    with pytest.raises(UnsupportedPlatformError):
        adapter.get_nice(1)
    with pytest.raises(UnsupportedPlatformError):
        adapter.set_nice(1, 10)
    with pytest.raises(UnsupportedPlatformError):
        adapter.get_affinity(1)
    with pytest.raises(UnsupportedPlatformError):
        adapter.set_affinity(1, [0])
    with pytest.raises(UnsupportedPlatformError):
        adapter.get_identity(1)


@LINUX_ONLY
def test_real_adapter_reports_support_on_linux() -> None:
    """On Linux the adapter permits enforcement attempts."""
    assert LinuxResourceAdapter().enforcement_supported is True


def test_access_denied_maps_to_permission_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kernel refusals surface as permission failures with context."""

    class DenyingProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def nice(self, value: int | None = None):
            raise psutil.AccessDenied(pid=self.pid)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(psutil, "Process", DenyingProcess)

    with pytest.raises(ResourcePermissionError):
        LinuxResourceAdapter().set_nice(1234, 10)


def test_gone_process_maps_to_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exits surface as not-found, not generic errors."""

    def gone(pid: int):
        raise psutil.NoSuchProcess(pid=pid)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(psutil, "Process", gone)

    with pytest.raises(ProcessNotFoundError):
        LinuxResourceAdapter().get_identity(1234)


def test_signal_safety_protects_parent_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """ARC never sends stop or continue signals to its untracked parent chain."""

    class Process:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def parents(self):
            return [Process(50)] if self.pid == 100 else []

        def create_time(self) -> float:
            return 1.0

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("arc.linux.psutil_adapter.os.getpid", lambda: 100)
    monkeypatch.setattr(psutil, "Process", Process)
    adapter = LinuxResourceAdapter()

    with pytest.raises(ResourceControlError, match="parent chain"):
        adapter.suspend_process(50)
    with pytest.raises(ResourceControlError, match="parent chain"):
        adapter.resume_process(50)


def test_tracked_suspend_can_be_restored_if_target_becomes_protected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Identity-pinned ARC suspensions remain resumable during restoration."""
    target_is_parent = False

    class Process:
        stopped = False

        def __init__(self, pid: int) -> None:
            self.pid = pid

        def parents(self):
            return [Process(200)] if self.pid == 100 and target_is_parent else []

        def create_time(self) -> float:
            return 2.0 if self.pid == 200 else 1.0

        def suspend(self) -> None:
            Process.stopped = True

        def resume(self) -> None:
            Process.stopped = False

        def status(self) -> str:
            return psutil.STATUS_STOPPED if Process.stopped else psutil.STATUS_RUNNING

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("arc.linux.psutil_adapter.os.getpid", lambda: 100)
    monkeypatch.setattr(psutil, "Process", Process)
    adapter = LinuxResourceAdapter()

    adapter.suspend_process(200)
    target_is_parent = True
    adapter.resume_process(200)

    assert Process.stopped is False


def test_fake_identity_roundtrip() -> None:
    """Fake identities carry PID plus creation time."""
    fake = make_fake(pid=50, create_time=1000.0, name="python")

    identity = fake.get_identity(50)

    assert (identity.pid, identity.create_time, identity.name) == (50, 1000.0, "python")


def test_fake_missing_process_raises_not_found() -> None:
    """Unknown PIDs fail like exited processes."""
    fake = make_fake()

    with pytest.raises(ProcessNotFoundError):
        fake.get_identity(9999)


def test_fake_injected_failures() -> None:
    """Injected failures mimic kernel refusals for rollback tests."""
    fake = make_fake(pid=50)
    fake.fail_on("set_affinity", 50)
    fake.deny_on("set_nice", 50)

    with pytest.raises(ResourceControlError):
        fake.set_affinity(50, [0])
    with pytest.raises(ResourcePermissionError):
        fake.set_nice(50, 10)


def test_fake_replace_simulates_pid_reuse() -> None:
    """Replacing a PID changes its lifetime identity."""
    fake = make_fake(pid=50, create_time=1000.0)

    fake.replace_process(50, create_time=2000.0)

    assert fake.get_identity(50).create_time == 2000.0


def test_fake_process_defaults() -> None:
    """Seed helper exposes the fake process fields tests rely on."""
    proc = FakeProcess(pid=7, create_time=1.0)

    assert proc.nice == 0
    assert proc.alive is True


def test_capabilities_report_honestly() -> None:
    """Capability detection matches the running platform."""
    capabilities = detect_capabilities()

    assert capabilities.platform == sys.platform
    assert capabilities.enforcement_supported is (sys.platform == "linux")
    if sys.platform != "linux":
        assert "Linux" in capabilities.reason
        assert capabilities.euid is None
