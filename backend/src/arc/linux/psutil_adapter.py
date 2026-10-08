"""Real Linux resource control built on psutil process APIs.

Linux only: every method refuses with ``UnsupportedPlatformError`` on
other platforms instead of pretending to work. Permission denials from
the kernel surface as ``ResourcePermissionError``. No shell, no sudo,
no escalation attempts. Suspending ARC's own runtime process is refused
outright so the engine can never deadlock itself with SIGSTOP.
"""

import os
import sys
import time
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

_STOP_VERIFY_ATTEMPTS = 5
_STOP_VERIFY_DELAY_SECONDS = 0.05


def _linux_start_time_ticks(pid: int, operation: str) -> int:
    """Read the kernel process start tick without wall-clock conversion."""
    try:
        stat = open(f"/proc/{pid}/stat", encoding="utf-8").read()
    except FileNotFoundError as exc:
        raise ProcessNotFoundError(operation, pid, "process no longer exists") from exc
    except PermissionError as exc:
        raise ResourcePermissionError(operation, pid, "cannot read procfs identity") from exc
    except OSError as exc:
        raise ResourceControlError(operation, pid, f"cannot read procfs identity: {exc}") from exc
    close = stat.rfind(")")
    try:
        # Fields after comm start at field 3. Index 19 is field 22, starttime.
        return int(stat[close + 2 :].split()[19])
    except (ValueError, IndexError) as exc:
        raise ResourceControlError(operation, pid, "malformed /proc process stat") from exc


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

    def __init__(self) -> None:
        self._suspended_by_arc: set[tuple[int, int]] = set()

    @staticmethod
    def _protected_pids() -> set[int]:
        """Return init, ARC, and ARC's current ancestor chain."""
        protected = {1, os.getpid()}
        try:
            current = psutil.Process(os.getpid())
            protected.update(parent.pid for parent in current.parents())
        except (psutil.Error, OSError):
            parent = os.getppid()
            if parent > 0:
                protected.add(parent)
        return protected

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
                start_time_ticks=_linux_start_time_ticks(pid, operation),
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

    def is_stopped(self, pid: int) -> bool:
        """True when the process currently sits in the stopped state."""
        operation = "is_stopped"
        proc = _process(operation, pid)
        try:
            return proc.status() == psutil.STATUS_STOPPED
        except psutil.NoSuchProcess as exc:
            raise ProcessNotFoundError(operation, pid, "process exited during inspection") from exc
        except psutil.AccessDenied as exc:
            raise ResourcePermissionError(
                operation, pid, "access denied while reading process state"
            ) from exc

    def suspend_process(self, pid: int) -> None:
        """Stop the process with SIGSTOP and verify it stopped."""
        operation = "suspend_process"
        if pid in self._protected_pids():
            raise ResourceControlError(
                operation, pid, "refusing to suspend ARC, its parent chain, or init"
            )
        proc = _process(operation, pid)
        try:
            identity = (pid, _linux_start_time_ticks(pid, operation))
            proc.suspend()
        except psutil.NoSuchProcess as exc:
            raise ProcessNotFoundError(operation, pid, "process exited before suspend") from exc
        except psutil.AccessDenied as exc:
            raise ResourcePermissionError(
                operation,
                pid,
                "kernel refused suspend (ownership or capability missing)",
            ) from exc
        self._await_state(proc, pid, operation, stopped=True)
        self._suspended_by_arc.add(identity)

    def resume_process(self, pid: int) -> None:
        """Continue the process with SIGCONT and verify it resumed."""
        operation = "resume_process"
        proc = _process(operation, pid)
        try:
            identity = (pid, _linux_start_time_ticks(pid, operation))
            if pid in self._protected_pids() and identity not in self._suspended_by_arc:
                raise ResourceControlError(
                    operation,
                    pid,
                    "refusing to resume ARC, its parent chain, or init",
                )
            proc.resume()
        except psutil.NoSuchProcess as exc:
            raise ProcessNotFoundError(operation, pid, "process exited before resume") from exc
        except psutil.AccessDenied as exc:
            raise ResourcePermissionError(
                operation,
                pid,
                "kernel refused resume (ownership or capability missing)",
            ) from exc
        self._await_state(proc, pid, operation, stopped=False)
        self._suspended_by_arc.discard(identity)

    @staticmethod
    def _await_state(proc: psutil.Process, pid: int, operation: str, stopped: bool) -> None:
        """Bounded poll until the process reaches the expected state."""
        want = "stopped" if stopped else "resumed"
        for _ in range(_STOP_VERIFY_ATTEMPTS):
            try:
                is_stopped = proc.status() == psutil.STATUS_STOPPED
            except psutil.NoSuchProcess as exc:
                raise ProcessNotFoundError(
                    operation, pid, "process exited during state verification"
                ) from exc
            except psutil.AccessDenied as exc:
                raise ResourcePermissionError(
                    operation, pid, "access denied during state verification"
                ) from exc
            if is_stopped == stopped:
                return
            time.sleep(_STOP_VERIFY_DELAY_SECONDS)
        raise ResourceControlError(
            operation, pid, f"process did not reach {want} state after SIGSTOP/SIGCONT"
        )

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
