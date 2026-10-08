"""Limited cgroups v2 integration: CPU quota (cpu.max) only.

ARC manages one leaf cgroup per targeted process under a scope directory
(``<root>/arc/arc-<pid>/``). Activation moves the process into its leaf,
records the previous effective cpu.max, and writes the contract quota.
Restoration writes the recorded value back, moves the process to its
original cgroup, and removes the leaf. Nothing else is managed: no
memory limits, no IO controls, no full cgroup manager.

Availability is detected honestly without mutating anything: v2 must expose
the cpu controller, enable it in ``cgroup.subtree_control``, and provide a
writable delegated root. These checks are still a hint, not a promise; the
kernel decides at use time and denials surface as explicit errors. Cgroup
problems never block ARC startup or non-cgroup contracts.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import psutil

from arc.linux.resources import (
    CgroupUnavailableError,
    ProcessNotFoundError,
    ResourceControlError,
    ResourcePermissionError,
)

logger = logging.getLogger(__name__)

SCOPE_NAME = "arc"
CPU_PERIOD = 100000
CGROUP_PROCS = "cgroup.procs"
CPU_MAX = "cpu.max"
SUBTREE_CONTROL = "cgroup.subtree_control"
DEFAULT_ROOT = Path("/sys/fs/cgroup")


def quota_to_cpu_max(quota_percent: float) -> str:
    """Map 1..100 percent onto a cpu.max quota string."""
    quota = max(1, min(CPU_PERIOD, int(quota_percent * 1000)))
    return f"{quota} {CPU_PERIOD}"


@dataclass(frozen=True)
class CgroupCapabilities:
    """What this host offers for cgroup enforcement."""

    available: bool
    version: str | None
    controllers: tuple[str, ...]
    writable_hint: bool | None
    reason: str


@dataclass(frozen=True)
class CgroupLease:
    """Prior cgroup state captured when a process entered ARC management."""

    pid: int
    create_time: float
    leaf: str
    origin: str
    previous_cpu_max: str


class CgroupManager(Protocol):
    """Small boundary for the one cgroup control ARC manages."""

    @property
    def supported(self) -> bool:
        """True only where real cgroup enforcement can run."""
        ...

    def capabilities(self) -> CgroupCapabilities:
        """Detect support without changing anything."""
        ...

    def enter(self, pid: int) -> CgroupLease:
        """Move the process into its ARC leaf. Returns prior state."""
        ...

    def set_quota(self, pid: int, quota_percent: float) -> None:
        """Write the cpu.max quota for the process leaf, verified by caller."""
        ...

    def get_quota(self, pid: int) -> str:
        """Read the current cpu.max content for the process leaf."""
        ...

    def leave(self, lease: CgroupLease) -> None:
        """Restore prior cpu.max, move the process home, remove the leaf."""
        ...


def _read_text(path: Path, operation: str, pid: int | None) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise CgroupUnavailableError(operation, pid, f"cgroup file missing: {path}") from exc
    except PermissionError as exc:
        raise ResourcePermissionError(operation, pid, f"cgroup file unreadable: {path}") from exc
    except OSError as exc:
        raise ResourceControlError(operation, pid, f"cgroup read failed: {path}: {exc}") from exc


def _write_text(path: Path, content: str, operation: str, pid: int | None) -> None:
    try:
        path.write_text(content, encoding="utf-8")
    except PermissionError as exc:
        raise ResourcePermissionError(
            operation, pid, f"cgroup write refused: {path} ({exc})"
        ) from exc
    except OSError as exc:
        raise CgroupUnavailableError(operation, pid, f"cgroup write failed: {path}: {exc}") from exc


class LinuxCgroupManager:
    """Real cgroups v2 cpu.max control. Safe to construct anywhere."""

    def __init__(self, root: Path | str = DEFAULT_ROOT, scope: str = SCOPE_NAME) -> None:
        self._root = Path(root)
        self._scope = scope

    @property
    def supported(self) -> bool:
        """True only on Linux with a v2 cpu controller visible."""
        return self.capabilities().available

    def capabilities(self) -> CgroupCapabilities:
        """Detect v2 cpu support by reading, never by writing."""
        if sys.platform != "linux":
            return CgroupCapabilities(
                available=False,
                version=None,
                controllers=(),
                writable_hint=False,
                reason=f"cgroup enforcement requires Linux (running on {sys.platform})",
            )
        controllers_file = self._root / "cgroup.controllers"
        if not controllers_file.is_file():
            return CgroupCapabilities(
                available=False,
                version=None,
                controllers=(),
                writable_hint=None,
                reason="no cgroups v2 hierarchy (cgroup.controllers missing)",
            )
        try:
            controllers = tuple(sorted(controllers_file.read_text(encoding="utf-8").split()))
        except OSError as exc:
            return CgroupCapabilities(
                available=False,
                version="v2",
                controllers=(),
                writable_hint=None,
                reason=f"cgroup.controllers unreadable: {exc}",
            )
        if "cpu" not in controllers:
            return CgroupCapabilities(
                available=False,
                version="v2",
                controllers=controllers,
                writable_hint=None,
                reason="cgroups v2 present but the cpu controller is not enabled",
            )
        subtree_file = self._root / SUBTREE_CONTROL
        try:
            enabled = tuple(sorted(subtree_file.read_text(encoding="utf-8").split()))
        except OSError as exc:
            return CgroupCapabilities(
                available=False,
                version="v2",
                controllers=controllers,
                writable_hint=None,
                reason=f"cgroup.subtree_control unreadable: {exc}",
            )
        if "cpu" not in enabled:
            return CgroupCapabilities(
                available=False,
                version="v2",
                controllers=controllers,
                writable_hint=os.access(self._root, os.W_OK),
                reason="cgroups v2 CPU controller is present but not enabled for child cgroups",
            )
        writable = os.access(self._root, os.W_OK)
        if not writable:
            return CgroupCapabilities(
                available=False,
                version="v2",
                controllers=controllers,
                writable_hint=False,
                reason=(
                    "cgroups v2 CPU controller detected, but no writable delegation is available"
                ),
            )
        return CgroupCapabilities(
            available=True,
            version="v2",
            controllers=controllers,
            writable_hint=True,
            reason="writable cgroups v2 CPU controller detected; each operation is still verified",
        )

    def _require_available(self, operation: str, pid: int | None) -> None:
        capabilities = self.capabilities()
        if not capabilities.available:
            raise CgroupUnavailableError(operation, pid, capabilities.reason)

    def _scope_dir(self) -> Path:
        return self._root / self._scope

    def _leaf_dir(self, pid: int) -> Path:
        return self._scope_dir() / f"arc-{pid}"

    def _origin_of(self, pid: int) -> Path:
        """Resolve the process current cgroup directory from /proc."""
        operation = "cgroup_origin"
        try:
            text = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ProcessNotFoundError(operation, pid, "process no longer exists") from exc
        except PermissionError as exc:
            raise ResourcePermissionError(operation, pid, "cannot inspect process cgroup") from exc
        except OSError as exc:
            raise CgroupUnavailableError(
                operation, pid, f"cannot read process cgroup: {exc}"
            ) from exc
        for line in text.splitlines():
            parts = line.strip().split(":")
            if len(parts) == 3 and parts[1] == "":
                return self._root / parts[2].lstrip("/")
        raise CgroupUnavailableError(
            operation, pid, "process is not in the unified cgroups v2 hierarchy"
        )

    def enter(self, pid: int) -> CgroupLease:
        """Move the process into its ARC leaf, recording prior cpu.max."""
        operation = "cgroup_enter"
        self._require_available(operation, pid)
        try:
            proc = psutil.Process(pid)
            create_time = float(proc.create_time())
        except psutil.NoSuchProcess as exc:
            raise ProcessNotFoundError(operation, pid, "process no longer exists") from exc
        except psutil.AccessDenied as exc:
            raise ResourcePermissionError(
                operation, pid, "access denied while opening process"
            ) from exc
        origin = self._origin_of(pid)
        previous = _read_text(origin / CPU_MAX, operation, pid)
        leaf = self._leaf_dir(pid)
        try:
            self._scope_dir().mkdir(exist_ok=True)
            leaf.mkdir(exist_ok=True)
        except PermissionError as exc:
            raise ResourcePermissionError(
                operation, pid, f"cannot create ARC cgroup ({exc})"
            ) from exc
        except OSError as exc:
            raise CgroupUnavailableError(
                operation, pid, f"cannot create ARC cgroup: {exc}"
            ) from exc
        _write_text(leaf / CPU_MAX, previous, operation, pid)
        _write_text(leaf / CGROUP_PROCS, str(pid), operation, pid)
        return CgroupLease(
            pid=pid,
            create_time=create_time,
            leaf=str(leaf),
            origin=str(origin),
            previous_cpu_max=previous,
        )

    def set_quota(self, pid: int, quota_percent: float) -> None:
        """Write the cpu.max quota for the process ARC leaf."""
        operation = "cgroup_set_quota"
        self._require_available(operation, pid)
        if not 1 <= quota_percent <= 100:
            raise CgroupUnavailableError(
                operation, pid, f"quota {quota_percent} outside 1..100 percent"
            )
        _write_text(self._leaf_dir(pid) / CPU_MAX, quota_to_cpu_max(quota_percent), operation, pid)

    def get_quota(self, pid: int) -> str:
        """Read the current cpu.max content for the process ARC leaf."""
        operation = "cgroup_get_quota"
        self._require_available(operation, pid)
        return _read_text(self._leaf_dir(pid) / CPU_MAX, operation, pid)

    def leave(self, lease: CgroupLease) -> None:
        """Write back prior cpu.max, move the process home, remove the leaf."""
        operation = "cgroup_leave"
        pid = lease.pid
        self._require_available(operation, pid)
        leaf = Path(lease.leaf)
        origin = Path(lease.origin)
        _write_text(leaf / CPU_MAX, lease.previous_cpu_max, operation, pid)
        _write_text(origin / CGROUP_PROCS, str(pid), operation, pid)
        try:
            leaf.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise CgroupUnavailableError(
                operation, pid, f"cannot remove ARC cgroup leaf: {exc}"
            ) from exc


class FakeCgroupManager:
    """In-memory cgroup stand-in for deterministic tests."""

    def __init__(self) -> None:
        self._quotas: dict[int, str] = {}
        self._origins: dict[int, str] = {}
        self._previous: dict[int, str] = {}
        self.fail_operations: set[str] = set()

    @property
    def supported(self) -> bool:
        """The fake always permits exercising cgroup logic."""
        return True

    def capabilities(self) -> CgroupCapabilities:
        """Fake reports available so logic paths execute."""
        return CgroupCapabilities(
            available=True,
            version="v2",
            controllers=("cpu", "memory"),
            writable_hint=True,
            reason="fake cgroup hierarchy for tests",
        )

    def _check(self, operation: str, pid: int | None) -> None:
        if operation in self.fail_operations:
            raise ResourcePermissionError(operation, pid, "injected cgroup failure")

    def enter(self, pid: int) -> CgroupLease:
        """Fake moving a process into ARC management."""
        self._check("cgroup_enter", pid)
        previous = self._previous.get(pid, "max 100000")
        self._quotas[pid] = previous
        self._origins[pid] = "fake:/origin"
        return CgroupLease(
            pid=pid,
            create_time=0.0,
            leaf=f"fake:/arc-{pid}",
            origin="fake:/origin",
            previous_cpu_max=previous,
        )

    def seed_previous(self, pid: int, cpu_max: str) -> None:
        """Set the fake prior cpu.max a process would have had."""
        self._previous[pid] = cpu_max

    def set_quota(self, pid: int, quota_percent: float) -> None:
        """Fake writing a cpu.max quota."""
        self._check("cgroup_set_quota", pid)
        if pid not in self._quotas:
            raise CgroupUnavailableError(
                "cgroup_set_quota", pid, "process is not under ARC management"
            )
        self._quotas[pid] = quota_to_cpu_max(quota_percent)

    def get_quota(self, pid: int) -> str:
        """Fake reading the current cpu.max content."""
        self._check("cgroup_get_quota", pid)
        try:
            return self._quotas[pid]
        except KeyError:
            raise CgroupUnavailableError(
                "cgroup_get_quota", pid, "process is not under ARC management"
            ) from None

    def leave(self, lease: CgroupLease) -> None:
        """Fake restoring quota, moving home, and removing the leaf."""
        pid = lease.pid
        self._check("cgroup_leave", pid)
        if pid not in self._quotas:
            raise CgroupUnavailableError("cgroup_leave", pid, "process is not under ARC management")
        self._quotas[pid] = lease.previous_cpu_max
        del self._quotas[pid]
        self._origins.pop(pid, None)
