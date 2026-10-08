"""Linux resource-control boundary: errors, identity, snapshots, adapter protocol.

This is the only place that names OS resource operations. Domain code in
``arc.enforcement``, ``arc.restoration``, and ``arc.core`` talks to
processes exclusively through ``ResourceAdapter``. The real
implementation lives in ``arc.linux.psutil_adapter``; deterministic
tests use ``arc.linux.fake_adapter``. There is no fake that reports
successful resource modification on unsupported platforms: every method
of the real adapter refuses clearly when not running on Linux.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProcessIdentity:
    """Stable-for-lifetime process identity.

    PID alone is unsafe because the kernel reuses PIDs. On Linux,
    ``start_time_ticks`` is field 22 from ``/proc/<pid>/stat`` and is the
    authoritative lifetime discriminator. ``create_time`` remains for
    display and adapters without procfs, but wall-clock boot-time drift
    must not decide whether restoration is safe.
    """

    pid: int
    create_time: float
    name: str | None = None
    start_time_ticks: int | None = None


def same_process(left: ProcessIdentity, right: ProcessIdentity) -> bool:
    """Return whether two identities describe the same process lifetime."""
    if left.pid != right.pid:
        return False
    if left.start_time_ticks is not None and right.start_time_ticks is not None:
        return left.start_time_ticks == right.start_time_ticks
    return left.create_time == right.create_time


@dataclass(frozen=True)
class ResourceSnapshot:
    """Exact prior resource values captured before ARC mutates anything.

    Only properties ARC intends to modify are captured (``None`` means
    untouched). Restoration writes these values back, never defaults.
    ``stopped`` records whether the process was already stopped before a
    suspend/resume action, so restoration returns it to the correct prior
    state. ``cpu_quota`` records the previous cgroups v2 cpu.max content
    with the ARC leaf and origin cgroup paths needed to restore it.
    """

    identity: ProcessIdentity
    nice: int | None = None
    affinity: tuple[int, ...] | None = None
    stopped: bool | None = None
    cpu_quota: str | None = None
    cgroup_leaf: str | None = None
    cgroup_origin: str | None = None


class ResourceControlError(Exception):
    """A resource operation failed. Carries where and what for logs."""

    def __init__(self, operation: str, pid: int | None, detail: str) -> None:
        super().__init__(f"{operation} (pid {pid}): {detail}")
        self.operation = operation
        self.pid = pid
        self.detail = detail


class UnsupportedPlatformError(ResourceControlError):
    """Raised when enforcement is attempted off Linux."""


class UnsupportedActionError(ResourceControlError):
    """Raised for action types with no execution implementation yet."""


class ProcessNotFoundError(ResourceControlError):
    """The process no longer exists (exited between steps)."""


class StaleProcessError(ResourceControlError):
    """The PID now refers to a different process lifetime. Never touch it."""


class ResourcePermissionError(ResourceControlError):
    """The kernel refused the operation (ownership or capability)."""


class InvalidCpusError(ResourceControlError):
    """Requested CPUs are not usable for the target process."""


class CgroupUnavailableError(ResourceControlError):
    """cgroups v2 enforcement is unavailable or refused for this target."""


class ResourceAdapter(Protocol):
    """Minimal interface the engine needs for process resource control."""

    @property
    def enforcement_supported(self) -> bool:
        """True only where real enforcement can run (Linux)."""
        ...

    def get_identity(self, pid: int) -> ProcessIdentity:
        """Return stable identity for a live process."""
        ...

    def get_nice(self, pid: int) -> int:
        """Read the current nice value."""
        ...

    def set_nice(self, pid: int, value: int) -> None:
        """Set the nice value. Must raise, never silently skip."""
        ...

    def get_affinity(self, pid: int) -> tuple[int, ...]:
        """Read the current CPU affinity as a sorted tuple."""
        ...

    def set_affinity(self, pid: int, cpus: Sequence[int]) -> None:
        """Set CPU affinity. Must raise, never silently skip."""
        ...

    def is_stopped(self, pid: int) -> bool:
        """True when the process is in the stopped (SIGSTOP) state."""
        ...

    def suspend_process(self, pid: int) -> None:
        """Stop the process with SIGSTOP and verify it stopped."""
        ...

    def resume_process(self, pid: int) -> None:
        """Continue the process with SIGCONT and verify it resumed."""
        ...
