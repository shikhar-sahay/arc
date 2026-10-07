"""Real Linux resource control built on psutil process APIs.

Linux only: every method refuses with ``UnsupportedPlatformError`` on
other platforms instead of pretending to work. Permission denials from
the kernel surface as ``ResourcePermissionError``. No shell, no sudo,
no escalation attempts.
"""

import sys
from collections.abc import Sequence

import psutil

from arc.linux.resources import (
    InvalidCpusError,
    ProcessIdentity,
    ProcessNotFoundError,
    ResourceControlError,
    ResourcePermissionError,
    UnsupportedPlatformError,
)


def _require_linux(operation: str, pid: int | None = None) -> None:
    if sys.platform != "linux":
        raise UnsupportedPlatformError(
            operation,
            pid,
            f"enforcement requires Linux (running on {sys.platform})",
        )


def _process(operation: str, pid: int) -> psutil.Process:
    _require_linux(operation, pid)
    try:
        return psutil.Process(pid)
    except psutil.NoSuchProcess as exc:
        raise ProcessNotFoundError(operation, pid, "process no longer exists") from exc
    except psutil.AccessDenied as exc:
        raise ResourcePermissionError(
            operation, pid, "access denied while opening process"
        ) from exc
    except psutil.ZombieProcess as exc:
        raise ProcessNotFoundError(operation, pid, "process is a zombie awaiting reaping") from exc


class LinuxResourceAdapter:
    """Real adapter. Safe to construct anywhere; use refuses off Linux."""

    @property
    def enforcement_supported(self) -> bool:
        """True only on Linux."""
        return sys.platform == "linux"

    def get_identity(self, pid: int) -> ProcessIdentity:
        """Identify a live process by PID plus creation time."""
        operation = "get_identity"
        proc = _process(operation, pid)
        try:
            return ProcessIdentity(
                pid=pid,
                create_time=float(proc.create_time()),
                name=proc.name(),
            )
        except psutil.NoSuchProcess as exc:
            raise ProcessNotFoundError(operation, pid, "process exited during inspection") from exc
        except psutil.AccessDenied as exc:
            raise ResourcePermissionError(
                operation, pid, "access denied while inspecting process"
            ) from exc

    def get_nice(self, pid: int) -> int:
        """Read the current nice value."""
        operation = "get_nice"
        proc = _process(operation, pid)
        try:
            return int(proc.nice())
        except psutil.NoSuchProcess as exc:
            raise ProcessNotFoundError(operation, pid, "process exited during inspection") from exc
        except psutil.AccessDenied as exc:
            raise ResourcePermissionError(
                operation, pid, "access denied while reading nice value"
            ) from exc

    def set_nice(self, pid: int, value: int) -> None:
        """Set the nice value. Lowering it may need privilege."""
        operation = "set_nice"
        proc = _process(operation, pid)
        try:
            proc.nice(int(value))
        except psutil.NoSuchProcess as exc:
            raise ProcessNotFoundError(
                operation, pid, "process exited before nice could be set"
            ) from exc
        except psutil.AccessDenied as exc:
            raise ResourcePermissionError(
                operation,
                pid,
                f"kernel refused nice={value} (ownership or capability missing)",
            ) from exc
        except (ValueError, OSError) as exc:
            raise ResourceControlError(operation, pid, f"nice={value} rejected: {exc}") from exc

    def get_affinity(self, pid: int) -> tuple[int, ...]:
        """Read the current CPU affinity as a sorted tuple."""
        operation = "get_affinity"
        proc = _process(operation, pid)
        try:
            return tuple(sorted(proc.cpu_affinity()))
        except psutil.NoSuchProcess as exc:
            raise ProcessNotFoundError(operation, pid, "process exited during inspection") from exc
        except psutil.AccessDenied as exc:
            raise ResourcePermissionError(
                operation, pid, "access denied while reading CPU affinity"
            ) from exc

    def set_affinity(self, pid: int, cpus: Sequence[int]) -> None:
        """Set CPU affinity. Invalid or disallowed CPUs fail explicitly."""
        operation = "set_affinity"
        wanted = sorted(set(int(cpu) for cpu in cpus))
        if not wanted or any(cpu < 0 for cpu in wanted):
            raise InvalidCpusError(operation, pid, f"invalid CPU set requested: {list(cpus)}")
        proc = _process(operation, pid)
        try:
            proc.cpu_affinity(wanted)
        except psutil.NoSuchProcess as exc:
            raise ProcessNotFoundError(
                operation, pid, "process exited before affinity could be set"
            ) from exc
        except psutil.AccessDenied as exc:
            raise ResourcePermissionError(
                operation,
                pid,
                f"kernel refused affinity={wanted} (ownership or capability missing)",
            ) from exc
        except (ValueError, OSError) as exc:
            raise InvalidCpusError(operation, pid, f"affinity={wanted} not usable: {exc}") from exc
