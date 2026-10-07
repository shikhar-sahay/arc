"""In-memory resource adapter for deterministic tests.

Behaves like the kernel in the ways tests need: stable creation times
per process lifetime, explicit failures for gone or replaced processes,
and optional injected failures. Used only in tests, never to misreport
real operations.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from arc.linux.resources import (
    ProcessIdentity,
    ProcessNotFoundError,
    ResourceControlError,
    ResourcePermissionError,
)


@dataclass
class FakeProcess:
    """One fake process lifetime."""

    pid: int
    create_time: float
    name: str | None = None
    nice: int = 0
    affinity: tuple[int, ...] = (0,)
    alive: bool = True


class FakeResourceAdapter:
    """Test double implementing the resource protocol in memory."""

    def __init__(self) -> None:
        self._processes: dict[int, FakeProcess] = {}
        self.calls: list[tuple[str, int, object]] = []
        self.fail_sets: set[tuple[str, int]] = set()
        self.deny_sets: set[tuple[str, int]] = set()

    @property
    def enforcement_supported(self) -> bool:
        """The fake always permits exercising enforcement logic."""
        return True

    def add_process(self, proc: FakeProcess) -> FakeProcess:
        """Register a fake process lifetime. Returns it for chaining."""
        self._processes[proc.pid] = proc
        return proc

    def remove_process(self, pid: int) -> None:
        """Simulate process exit."""
        proc = self._processes.get(pid)
        if proc is not None:
            proc.alive = False

    def replace_process(self, pid: int, create_time: float) -> FakeProcess:
        """Simulate PID reuse by a new process lifetime."""
        proc = FakeProcess(pid=pid, create_time=create_time)
        self._processes[pid] = proc
        return proc

    def fail_on(self, operation: str, pid: int) -> None:
        """Make the next matching mutation raise a generic failure."""
        self.fail_sets.add((operation, pid))

    def deny_on(self, operation: str, pid: int) -> None:
        """Make the next matching mutation raise a permission failure."""
        self.deny_sets.add((operation, pid))

    def _live(self, operation: str, pid: int) -> FakeProcess:
        proc = self._processes.get(pid)
        if proc is None or not proc.alive:
            raise ProcessNotFoundError(operation, pid, "process no longer exists")
        return proc

    def _check_injected(self, operation: str, pid: int) -> None:
        if (operation, pid) in self.deny_sets:
            raise ResourcePermissionError(operation, pid, "injected permission failure for test")
        if (operation, pid) in self.fail_sets:
            raise ResourceControlError(operation, pid, "injected operation failure for test")

    def get_identity(self, pid: int) -> ProcessIdentity:
        """Return the fake stable identity for a live process."""
        proc = self._live("get_identity", pid)
        return ProcessIdentity(pid=pid, create_time=proc.create_time, name=proc.name)

    def get_nice(self, pid: int) -> int:
        """Read the fake nice value."""
        return self._live("get_nice", pid).nice

    def set_nice(self, pid: int, value: int) -> None:
        """Set the fake nice value, honoring injected failures."""
        self._check_injected("set_nice", pid)
        proc = self._live("set_nice", pid)
        self.calls.append(("set_nice", pid, value))
        proc.nice = int(value)

    def get_affinity(self, pid: int) -> tuple[int, ...]:
        """Read the fake CPU affinity."""
        return self._live("get_affinity", pid).affinity

    def set_affinity(self, pid: int, cpus: Sequence[int]) -> None:
        """Set the fake CPU affinity, honoring injected failures."""
        self._check_injected("set_affinity", pid)
        proc = self._live("set_affinity", pid)
        wanted = tuple(sorted(set(int(cpu) for cpu in cpus)))
        if not wanted or any(cpu < 0 for cpu in wanted):
            raise ResourceControlError(
                "set_affinity", pid, f"invalid CPU set requested: {list(cpus)}"
            )
        self.calls.append(("set_affinity", pid, wanted))
        proc.affinity = wanted

    def set_calls_for(self, operation: str, pid: int) -> list[object]:
        """Values passed to one mutation, in call order (order assertions)."""
        return [value for op, call_pid, value in self.calls if op == operation and call_pid == pid]
