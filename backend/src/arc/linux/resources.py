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

    PID alone is unsafe because the kernel reuses PIDs. The creation
    time pins an identity to one process lifetime. ARC verifies this
    pair before restoring state so it never writes onto a reused PID.
    """

    pid: int
    create_time: float
    name: str | None = None


@dataclass(frozen=True)
class ResourceSnapshot:
    """Exact prior resource values captured before ARC mutates anything.

    Only properties ARC intends to modify are captured (``None`` means
    untouched). Restoration writes these values back, never defaults.
    """

    identity: ProcessIdentity
    nice: int | None = None
    affinity: tuple[int, ...] | None = None


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


class ResourceAdapter(Protocol):
    """Minimal interface the engine needs for nice/affinity control."""

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
