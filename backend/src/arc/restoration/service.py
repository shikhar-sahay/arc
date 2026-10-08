"""Restoration execution: write back exact snapshots, verify, stay honest.

For each snapshot the engine re-identifies the process by PID plus
creation time. Exited processes need no restoration. A PID whose
creation time changed now belongs to a different process lifetime and
is never touched: that is a stale-target failure. Restored values are
read back and verified.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from arc.linux.resources import (
    ProcessNotFoundError,
    ResourceAdapter,
    ResourceControlError,
    ResourceSnapshot,
    same_process,
)

if TYPE_CHECKING:
    from arc.linux.cgroups import CgroupManager


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RestoreEntry:
    """What happened for one snapshot."""

    pid: int
    status: str
    detail: str = ""


@dataclass
class RestorationResult:
    """Outcome of restoring a set of snapshots."""

    ok: bool
    entries: list[RestoreEntry] = field(default_factory=list)

    @property
    def restored(self) -> list[int]:
        """PIDs restored and verified."""
        return [entry.pid for entry in self.entries if entry.status == "restored"]

    @property
    def disappeared(self) -> list[int]:
        """PIDs whose process exited (nothing left to restore)."""
        return [entry.pid for entry in self.entries if entry.status == "disappeared"]

    @property
    def stale(self) -> list[int]:
        """PIDs reused by a new lifetime (deliberately untouched)."""
        return [entry.pid for entry in self.entries if entry.status == "stale"]

    @property
    def failed(self) -> list[int]:
        """PIDs whose restoration failed and need attention."""
        return [entry.pid for entry in self.entries if entry.status == "failed"]


def restore_snapshots(
    snapshots: list[ResourceSnapshot],
    adapter: ResourceAdapter,
    cgroup_manager: CgroupManager | None = None,
) -> RestorationResult:
    """Restore exact captured values with identity checks and verification."""
    from arc.linux.cgroups import CgroupLease, CgroupManager  # noqa: F401

    entries: list[RestoreEntry] = []
    for snapshot in sorted(snapshots, key=lambda snap: snap.identity.pid):
        pid = snapshot.identity.pid
        try:
            current = adapter.get_identity(pid)
        except ProcessNotFoundError:
            entries.append(RestoreEntry(pid=pid, status="disappeared", detail="process exited"))
            continue
        except ResourceControlError as exc:
            entries.append(RestoreEntry(pid=pid, status="failed", detail=str(exc)))
            continue
        if not same_process(current, snapshot.identity):
            logger.error(
                "pid %s reused by a new process lifetime, refusing restoration",
                pid,
            )
            entries.append(
                RestoreEntry(
                    pid=pid,
                    status="stale",
                    detail="PID reused by a different process, left untouched",
                )
            )
            continue
        try:
            if snapshot.nice is not None:
                adapter.set_nice(pid, snapshot.nice)
                if adapter.get_nice(pid) != snapshot.nice:
                    raise ResourceControlError(
                        "restore_verify", pid, f"nice {snapshot.nice} did not take effect"
                    )
            if snapshot.affinity is not None:
                adapter.set_affinity(pid, list(snapshot.affinity))
                if tuple(sorted(adapter.get_affinity(pid))) != tuple(sorted(snapshot.affinity)):
                    raise ResourceControlError(
                        "restore_verify",
                        pid,
                        f"affinity {list(snapshot.affinity)} did not take effect",
                    )
            if snapshot.stopped is not None:
                is_curr_stopped = adapter.is_stopped(pid)
                if snapshot.stopped != is_curr_stopped:
                    if snapshot.stopped:
                        adapter.suspend_process(pid)
                    else:
                        adapter.resume_process(pid)
                if adapter.is_stopped(pid) != snapshot.stopped:
                    raise ResourceControlError(
                        "restore_verify",
                        pid,
                        f"process stopped state {snapshot.stopped} did not take effect",
                    )
            if snapshot.cpu_quota is not None and cgroup_manager is not None:
                assert snapshot.cgroup_leaf is not None
                assert snapshot.cgroup_origin is not None
                lease = CgroupLease(
                    pid=pid,
                    create_time=snapshot.identity.create_time,
                    leaf=snapshot.cgroup_leaf,
                    origin=snapshot.cgroup_origin,
                    previous_cpu_max=snapshot.cpu_quota,
                )
                cgroup_manager.leave(lease)
        except ResourceControlError as exc:
            logger.error("restoration failed for pid %s: %s", pid, exc)
            entries.append(RestoreEntry(pid=pid, status="failed", detail=str(exc)))
            continue
        entries.append(RestoreEntry(pid=pid, status="restored"))
    result = RestorationResult(ok=True, entries=entries)
    result.ok = not result.failed and not result.stale
    return result
