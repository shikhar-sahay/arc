"""Activation orchestration: snapshot, apply, verify, rollback.

Action order is deterministic: contract action order on the outside,
ascending PID on the inside. All snapshots are captured before anything
is mutated. If any operation fails, every mutation already performed in
that attempt is rolled back in reverse journal order before reporting
ERROR. Rollback problems are surfaced, never hidden.
"""

import logging
from dataclasses import dataclass, field

from arc.contracts.models import (
    Contract,
    CpuAffinityAction,
    CpuQuotaAction,
    NiceAction,
    ResumeAction,
    SuspendAction,
)
from arc.linux.cgroups import CgroupLease, CgroupManager
from arc.linux.resources import (
    ResourceAdapter,
    ResourceControlError,
    ResourceSnapshot,
)
from arc.monitoring.processes import ProcessObservation

logger = logging.getLogger(__name__)

SUPPORTED_ACTION_TYPES = ("nice", "cpu_affinity", "suspend", "resume", "cpu_quota")


@dataclass(frozen=True)
class AppliedOperation:
    """One verified mutation, kept so rollback can undo it."""

    pid: int
    action_index: int
    kind: str
    previous: int | tuple[int, ...] | bool | CgroupLease
    requested: int | tuple[int, ...] | bool | float


@dataclass
class ActivationFailure:
    """Why activation failed and whether rollback completed."""

    error: str
    rolled_back: bool
    rollback_errors: list[str] = field(default_factory=list)


@dataclass
class ActivationResult:
    """Outcome of one activation attempt."""

    ok: bool
    snapshots: list[ResourceSnapshot] = field(default_factory=list)
    applied: list[AppliedOperation] = field(default_factory=list)
    failure: ActivationFailure | None = None


def _needs_nice(contract: Contract) -> bool:
    return any(action.type == "nice" for action in contract.actions)


def _needs_affinity(contract: Contract) -> bool:
    return any(action.type == "cpu_affinity" for action in contract.actions)


def _needs_stopped(contract: Contract) -> bool:
    return any(action.type in ("suspend", "resume") for action in contract.actions)


def _needs_cgroup(contract: Contract) -> bool:
    return any(action.type == "cpu_quota" for action in contract.actions)


def _capture_snapshots(
    contract: Contract,
    targets: list[ProcessObservation],
    adapter: ResourceAdapter,
    cgroup_manager: CgroupManager | None = None,
) -> tuple[list[ResourceSnapshot], dict[int, CgroupLease]]:
    want_nice = _needs_nice(contract)
    want_affinity = _needs_affinity(contract)
    want_stopped = _needs_stopped(contract)
    want_cgroup = _needs_cgroup(contract)

    if want_cgroup:
        if cgroup_manager is None or not cgroup_manager.supported:
            raise ResourceControlError(
                "cgroup_precheck",
                None,
                "cgroups v2 enforcement is unavailable on this host",
            )

    snapshots: list[ResourceSnapshot] = []
    leases: dict[int, CgroupLease] = {}

    for target in targets:
        identity = adapter.get_identity(target.pid)
        cgroup_lease: CgroupLease | None = None
        if want_cgroup and cgroup_manager is not None:
            cgroup_lease = cgroup_manager.enter(target.pid)
            leases[target.pid] = cgroup_lease

        snapshots.append(
            ResourceSnapshot(
                identity=identity,
                nice=adapter.get_nice(target.pid) if want_nice else None,
                affinity=adapter.get_affinity(target.pid) if want_affinity else None,
                stopped=adapter.is_stopped(target.pid) if want_stopped else None,
                cpu_quota=cgroup_lease.previous_cpu_max if cgroup_lease else None,
                cgroup_leaf=cgroup_lease.leaf if cgroup_lease else None,
                cgroup_origin=cgroup_lease.origin if cgroup_lease else None,
            )
        )
    return snapshots, leases


def _apply_nice(adapter: ResourceAdapter, pid: int, value: int) -> AppliedOperation | str:
    previous = adapter.get_nice(pid)
    adapter.set_nice(pid, value)
    actual = adapter.get_nice(pid)
    if actual != value:
        return f"nice verification failed on pid {pid}: wanted {value}, read {actual}"
    return AppliedOperation(
        pid=pid, action_index=-1, kind="nice", previous=previous, requested=value
    )


def _apply_affinity(adapter: ResourceAdapter, pid: int, cpus: list[int]) -> AppliedOperation | str:
    previous = adapter.get_affinity(pid)
    wanted = tuple(sorted(set(cpus)))
    adapter.set_affinity(pid, wanted)
    actual = tuple(sorted(adapter.get_affinity(pid)))
    if actual != wanted:
        return (
            f"affinity verification failed on pid {pid}: wanted {list(wanted)}, read {list(actual)}"
        )
    return AppliedOperation(
        pid=pid, action_index=-1, kind="cpu_affinity", previous=previous, requested=wanted
    )


def _apply_suspend(adapter: ResourceAdapter, pid: int) -> AppliedOperation | str:
    previous = adapter.is_stopped(pid)
    adapter.suspend_process(pid)
    if not adapter.is_stopped(pid):
        return f"suspend verification failed on pid {pid}: process is not stopped"
    return AppliedOperation(
        pid=pid, action_index=-1, kind="suspend", previous=previous, requested=True
    )


def _apply_resume(adapter: ResourceAdapter, pid: int) -> AppliedOperation | str:
    previous = adapter.is_stopped(pid)
    adapter.resume_process(pid)
    if adapter.is_stopped(pid):
        return f"resume verification failed on pid {pid}: process is still stopped"
    return AppliedOperation(
        pid=pid, action_index=-1, kind="resume", previous=previous, requested=False
    )


def _apply_quota(
    cgroup_manager: CgroupManager, pid: int, quota_percent: float, lease: CgroupLease
) -> AppliedOperation | str:
    cgroup_manager.set_quota(pid, quota_percent)
    actual = cgroup_manager.get_quota(pid)
    from arc.linux.cgroups import quota_to_cpu_max

    expected = quota_to_cpu_max(quota_percent)
    if actual != expected:
        return f"cpu_quota verification failed on pid {pid}: wanted {expected!r}, read {actual!r}"
    return AppliedOperation(
        pid=pid, action_index=-1, kind="cpu_quota", previous=lease, requested=quota_percent
    )


def _rollback(
    applied: list[AppliedOperation],
    adapter: ResourceAdapter,
    cgroup_manager: CgroupManager | None = None,
) -> list[str]:
    errors: list[str] = []
    for op in reversed(applied):
        try:
            if op.kind == "nice":
                assert isinstance(op.previous, int)
                adapter.set_nice(op.pid, op.previous)
                if adapter.get_nice(op.pid) != op.previous:
                    errors.append(f"pid {op.pid}: nice rollback unverified")
            elif op.kind == "cpu_affinity":
                assert isinstance(op.previous, tuple)
                adapter.set_affinity(op.pid, list(op.previous))
                if tuple(sorted(adapter.get_affinity(op.pid))) != tuple(sorted(op.previous)):
                    errors.append(f"pid {op.pid}: affinity rollback unverified")
            elif op.kind == "suspend":
                assert isinstance(op.previous, bool)
                if not op.previous:
                    adapter.resume_process(op.pid)
                    if adapter.is_stopped(op.pid):
                        errors.append(f"pid {op.pid}: suspend rollback unverified")
            elif op.kind == "resume":
                assert isinstance(op.previous, bool)
                if op.previous:
                    adapter.suspend_process(op.pid)
                    if not adapter.is_stopped(op.pid):
                        errors.append(f"pid {op.pid}: resume rollback unverified")
            elif op.kind == "cpu_quota":
                if cgroup_manager is not None:
                    assert isinstance(op.previous, CgroupLease)
                    cgroup_manager.leave(op.previous)
        except ResourceControlError as exc:
            errors.append(f"pid {op.pid}: rollback of {op.kind} failed: {exc.detail}")
    return errors


def activate_contract(
    contract: Contract,
    targets: list[ProcessObservation],
    adapter: ResourceAdapter,
    cgroup_manager: CgroupManager | None = None,
) -> ActivationResult:
    """Snapshot, apply in order, verify, or roll back. Never half-applies."""
    if not adapter.enforcement_supported:
        return ActivationResult(
            ok=False,
            failure=ActivationFailure(error="enforcement requires Linux", rolled_back=True),
        )
    unsupported = sorted({action.type for action in contract.actions} - set(SUPPORTED_ACTION_TYPES))
    if unsupported:
        return ActivationResult(
            ok=False,
            failure=ActivationFailure(
                error=f"unsupported action types (not executed): {', '.join(unsupported)}",
                rolled_back=True,
            ),
        )
    ordered = sorted(targets, key=lambda obs: obs.pid)
    try:
        snapshots, leases = _capture_snapshots(contract, ordered, adapter, cgroup_manager)
    except ResourceControlError as exc:
        logger.warning("contract %s snapshot failed: %s", contract.id, exc)
        return ActivationResult(
            ok=False,
            failure=ActivationFailure(error=f"snapshot failed: {exc}", rolled_back=True),
        )
    applied: list[AppliedOperation] = []
    try:
        for index, action in enumerate(contract.actions):
            for target in ordered:
                if action.type == "nice":
                    assert isinstance(action, NiceAction)
                    result = _apply_nice(adapter, target.pid, action.value)
                elif action.type == "cpu_affinity":
                    assert isinstance(action, CpuAffinityAction)
                    result = _apply_affinity(adapter, target.pid, list(action.cpus))
                elif action.type == "suspend":
                    assert isinstance(action, SuspendAction)
                    result = _apply_suspend(adapter, target.pid)
                elif action.type == "resume":
                    assert isinstance(action, ResumeAction)
                    result = _apply_resume(adapter, target.pid)
                elif action.type == "cpu_quota":
                    assert isinstance(action, CpuQuotaAction)
                    if cgroup_manager is None:
                        raise ResourceControlError(
                            "cpu_quota", target.pid, "cgroups manager not configured"
                        )
                    result = _apply_quota(
                        cgroup_manager, target.pid, action.quota_percent, leases[target.pid]
                    )
                else:  # pragma: no cover, precheck rejects anything else
                    raise ResourceControlError(
                        "precheck", target.pid, f"unsupported action: {action.type}"
                    )
                if isinstance(result, str):
                    raise ResourceControlError("verify", target.pid, result)
                applied.append(
                    AppliedOperation(
                        pid=result.pid,
                        action_index=index,
                        kind=result.kind,
                        previous=result.previous,
                        requested=result.requested,
                    )
                )
    except ResourceControlError as exc:
        logger.warning("contract %s activation failed: %s", contract.id, exc)
        rollback_errors = _rollback(applied, adapter, cgroup_manager)
        # Any remaining leases not yet rolled back via applied operations
        for pid, lease in leases.items():
            if not any(op.kind == "cpu_quota" and op.pid == pid for op in applied):
                if cgroup_manager is not None:
                    try:
                        cgroup_manager.leave(lease)
                    except ResourceControlError as l_exc:
                        rollback_errors.append(f"pid {pid}: cgroup lease cleanup failed: {l_exc}")
        if rollback_errors:
            logger.error("contract %s rollback incomplete: %s", contract.id, rollback_errors)
        return ActivationResult(
            ok=False,
            snapshots=snapshots,
            applied=applied,
            failure=ActivationFailure(
                error=str(exc),
                rolled_back=not rollback_errors,
                rollback_errors=rollback_errors,
            ),
        )
    return ActivationResult(ok=True, snapshots=snapshots, applied=applied)
