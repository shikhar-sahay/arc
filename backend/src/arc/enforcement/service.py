"""Activation orchestration: snapshot, apply, verify, rollback.

Action order is deterministic: contract action order on the outside,
ascending PID on the inside. All snapshots are captured before anything
is mutated. If any operation fails, every mutation already performed in
that attempt is rolled back in reverse journal order before reporting
ERROR. Rollback problems are surfaced, never hidden.
"""

import logging
from dataclasses import dataclass, field

from arc.contracts.models import Contract, CpuAffinityAction, NiceAction
from arc.linux.resources import (
    ResourceAdapter,
    ResourceControlError,
    ResourceSnapshot,
)
from arc.monitoring.processes import ProcessObservation

logger = logging.getLogger(__name__)

SUPPORTED_ACTION_TYPES = ("nice", "cpu_affinity")


@dataclass(frozen=True)
class AppliedOperation:
    """One verified mutation, kept so rollback can undo it."""

    pid: int
    action_index: int
    kind: str
    previous: int | tuple[int, ...]
    requested: int | tuple[int, ...]


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


def _capture_snapshots(
    contract: Contract,
    targets: list[ProcessObservation],
    adapter: ResourceAdapter,
) -> list[ResourceSnapshot]:
    want_nice = _needs_nice(contract)
    want_affinity = _needs_affinity(contract)
    snapshots: list[ResourceSnapshot] = []
    for target in targets:
        identity = adapter.get_identity(target.pid)
        snapshots.append(
            ResourceSnapshot(
                identity=identity,
                nice=adapter.get_nice(target.pid) if want_nice else None,
                affinity=adapter.get_affinity(target.pid) if want_affinity else None,
            )
        )
    return snapshots


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


def _rollback(applied: list[AppliedOperation], adapter: ResourceAdapter) -> list[str]:
    errors: list[str] = []
    for op in reversed(applied):
        try:
            if op.kind == "nice":
                assert isinstance(op.previous, int)
                adapter.set_nice(op.pid, op.previous)
                if adapter.get_nice(op.pid) != op.previous:
                    errors.append(f"pid {op.pid}: nice rollback unverified")
            else:
                assert isinstance(op.previous, tuple)
                adapter.set_affinity(op.pid, list(op.previous))
                if tuple(sorted(adapter.get_affinity(op.pid))) != tuple(sorted(op.previous)):
                    errors.append(f"pid {op.pid}: affinity rollback unverified")
        except ResourceControlError as exc:
            errors.append(f"pid {op.pid}: rollback of {op.kind} failed: {exc.detail}")
    return errors


def activate_contract(
    contract: Contract,
    targets: list[ProcessObservation],
    adapter: ResourceAdapter,
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
        snapshots = _capture_snapshots(contract, ordered, adapter)
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
        rollback_errors = _rollback(applied, adapter)
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
