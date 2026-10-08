"""Persistent ARC runtime engine: monitor, evaluate, enforce, restore.

The engine is the source of truth. It owns contracts, per-contract
runtime state, the event history, and the latest snapshots. HTTP GET
endpoints only read this state; they never drive enforcement.

One synchronous ``step()`` performs a full cycle under a short lock, so
API reads never see half-mutated structures. The async loop only
schedules steps. Nothing starts on import: callers use ``start()`` plus
``run_forever()``, or drive ``step()`` directly in tests.
"""

import asyncio
import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from arc.contracts.models import Contract
from arc.core.lifecycle import (
    ContractRuntimeState,
    EvaluationOutcome,
    LifecycleState,
)
from arc.enforcement.service import activate_contract
from arc.evaluation.service import (
    ContractEvaluation,
    evaluate_contract,
    evaluate_restore,
)
from arc.linux.capabilities import PlatformCapabilities, detect_capabilities
from arc.linux.cgroups import CgroupManager, LinuxCgroupManager
from arc.linux.psutil_adapter import LinuxResourceAdapter
from arc.linux.resources import (
    ProcessIdentity,
    ProcessNotFoundError,
    ResourceAdapter,
    ResourceControlError,
    ResourceSnapshot,
)
from arc.monitoring.processes import (
    ProcessObservation,
    resolve_process_target,
    sample_processes,
)
from arc.monitoring.system import SystemMonitor, SystemSnapshot
from arc.observability.events import ArcEvent, ArcEventType, EventLog
from arc.restoration.service import restore_snapshots

logger = logging.getLogger(__name__)


def _action_resource(action_type: str) -> str:
    """Return the independently owned process resource for an action."""
    if action_type in ("suspend", "resume"):
        return "process_state"
    return action_type


@dataclass(frozen=True)
class ContractStatusView:
    """Copy of one contract plus its runtime state, safe to hand out."""

    contract: Contract
    lifecycle: LifecycleState
    outcome: EvaluationOutcome | None
    matched_pids: list[int]
    active_identities: list[ProcessIdentity]
    trigger_raw: bool | None
    trigger_satisfied: bool | None
    restore_raw: bool | None
    restore_satisfied: bool | None
    activated_at: float | None
    last_error: str | None
    trigger_elapsed_seconds: float | None
    restore_elapsed_seconds: float | None


@dataclass(frozen=True)
class EngineStatusView:
    """Copy of engine health, safe to hand out."""

    running: bool
    platform: str
    enforcement_supported: bool
    euid: int | None
    privileged_hint: bool | None
    poll_interval_seconds: float
    contract_count: int
    active_contracts: int
    error_contracts: int
    event_count: int
    cgroup_available: bool = False
    cgroup_reason: str = ""


@dataclass
class EngineCycle:
    """Everything observed and decided in one polling cycle."""

    telemetry: SystemSnapshot
    process_count: int
    evaluations: list[ContractEvaluation] = field(default_factory=list)


class ObservationEngine:
    """Runs the full contract lifecycle without any HTTP involvement."""

    def __init__(
        self,
        contracts: Sequence[Contract] = (),
        poll_interval_seconds: float = 5.0,
        system_monitor: SystemMonitor | None = None,
        process_sampler: Callable[[], list[ProcessObservation]] | None = None,
        resource_adapter: ResourceAdapter | None = None,
        cgroup_manager: CgroupManager | None = None,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._contracts = list(contracts)
        self.poll_interval_seconds = poll_interval_seconds
        self._monitor = system_monitor or SystemMonitor()
        self._process_sampler = process_sampler or sample_processes
        self._adapter = resource_adapter or LinuxResourceAdapter()
        self._cgroup_manager: CgroupManager = cgroup_manager or LinuxCgroupManager()
        self._capabilities = detect_capabilities()
        self._events = EventLog()
        self._lock = threading.Lock()
        self._running = False
        self._latest_telemetry: SystemSnapshot | None = None
        self._latest_observations: list[ProcessObservation] = []
        self._runtimes = {
            contract.id: ContractRuntimeState(contract_id=contract.id)
            for contract in self._contracts
        }
        for contract in self._contracts:
            runtime = self._runtimes[contract.id]
            runtime.trigger_tracker.required_seconds = contract.trigger.for_seconds
            runtime.restore_tracker.required_seconds = contract.restore.for_seconds

    @property
    def contracts(self) -> list[Contract]:
        """Loaded contract definitions (configuration, not runtime state)."""
        return list(self._contracts)

    @property
    def resource_adapter(self) -> ResourceAdapter:
        """Resource adapter used for read-only process enrichment."""
        return self._adapter

    @property
    def capabilities(self) -> PlatformCapabilities:
        """Platform and privilege report."""
        return self._capabilities

    def runtime_for(self, contract_id: str) -> ContractRuntimeState | None:
        """Transient runtime state for one contract, if known."""
        return self._runtimes.get(contract_id)

    def start(self) -> None:
        """Mark the engine running and record the start event."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._events.record(
                ArcEventType.ENGINE_STARTED,
                f"ARC engine started with {len(self._contracts)} contract(s), "
                f"enforcement_supported={self._capabilities.enforcement_supported}",
            )
            logger.info("ARC engine started")

    def reset_contract(self, contract_id: str) -> bool:
        """Manually recover an ERROR contract back to INACTIVE."""
        with self._lock:
            runtime = self._runtimes.get(contract_id)
            if runtime is None or runtime.lifecycle is not LifecycleState.ERROR:
                return False
            if runtime.snapshots:
                contract = next(c for c in self._contracts if c.id == contract_id)
                error = self._settle_snapshots(
                    contract,
                    runtime,
                    reason="manual recovery",
                    now=time.monotonic(),
                )
                if error is not None:
                    return False
                logger.info("contract %s recovered after restoration", contract_id)
                return True
            runtime.reset_error()
            logger.info("contract %s manually reset to inactive", contract_id)
            return True

    def reload_contracts(self, new_contracts: Sequence[Contract]) -> None:
        """Reload contract definitions atomically without disrupting live monitoring.

        Preserves existing runtimes for active/restoring/error contracts where IDs match.
        For new contracts, initializes clean runtime state.
        For removed contracts:
        - If active or restoring, raises ValueError to protect active enforcement.
        - Otherwise, drops runtime state cleanly.
        """
        with self._lock:
            new_contract_map = {c.id: c for c in new_contracts}
            old_contract_map = {c.id: c for c in self._contracts}
            protected = (
                LifecycleState.ACTIVE,
                LifecycleState.ACTIVATING,
                LifecycleState.RESTORING,
            )
            # Validate the entire replacement before mutating definitions or trackers.
            for old_id, runtime in self._runtimes.items():
                if runtime.lifecycle not in protected:
                    continue
                replacement = new_contract_map.get(old_id)
                if replacement is None:
                    raise ValueError(
                        f"cannot remove contract {old_id} while in state {runtime.lifecycle.value}"
                    )
                if replacement != old_contract_map[old_id]:
                    raise ValueError(
                        f"cannot modify contract {old_id} while in state {runtime.lifecycle.value}"
                    )

            updated_runtimes: dict[str, ContractRuntimeState] = {}
            for contract in new_contracts:
                if contract.id in self._runtimes:
                    # Preserve existing runtime state
                    rt = self._runtimes[contract.id]
                    rt.trigger_tracker.required_seconds = contract.trigger.for_seconds
                    rt.restore_tracker.required_seconds = contract.restore.for_seconds
                    updated_runtimes[contract.id] = rt
                else:
                    rt = ContractRuntimeState(contract_id=contract.id)
                    rt.trigger_tracker.required_seconds = contract.trigger.for_seconds
                    rt.restore_tracker.required_seconds = contract.restore.for_seconds
                    updated_runtimes[contract.id] = rt

            self._contracts = list(new_contracts)
            self._runtimes = updated_runtimes
            logger.info("reloaded %d contract(s) into engine", len(self._contracts))

    def enable_contract(
        self,
        contract_id: str,
        enabled: bool,
        persist: Callable[[Contract], None] | None = None,
    ) -> Contract:
        """Toggle enabled flag for a contract definition."""
        with self._lock:
            idx = next((i for i, c in enumerate(self._contracts) if c.id == contract_id), None)
            if idx is None:
                raise KeyError(f"contract {contract_id} not found")
            current = self._contracts[idx]
            if current.enabled == enabled:
                return current
            runtime = self._runtimes[contract_id]
            if runtime.lifecycle in (
                LifecycleState.ACTIVATING,
                LifecycleState.ACTIVE,
                LifecycleState.RESTORING,
            ):
                raise ValueError(
                    f"cannot change enabled state for contract {contract_id} while in state "
                    f"{runtime.lifecycle.value}"
                )
            updated = current.model_copy(update={"enabled": enabled})
            if persist is not None:
                persist(updated)
            self._contracts[idx] = updated
            return updated

    def set_contract(self, contract: Contract) -> None:
        """Add or update a contract definition in memory.

        Refuses update if the existing contract is currently ACTIVE, ACTIVATING, or RESTORING.
        """
        with self._lock:
            runtime = self._runtimes.get(contract.id)
            if runtime is not None and runtime.lifecycle in (
                LifecycleState.ACTIVE,
                LifecycleState.ACTIVATING,
                LifecycleState.RESTORING,
            ):
                raise ValueError(
                    f"cannot modify contract {contract.id} while in state {runtime.lifecycle.value}"
                )

            idx = next((i for i, c in enumerate(self._contracts) if c.id == contract.id), None)
            if idx is not None:
                self._contracts[idx] = contract
            else:
                self._contracts.append(contract)

            if runtime is None:
                rt = ContractRuntimeState(contract_id=contract.id)
                rt.trigger_tracker.required_seconds = contract.trigger.for_seconds
                rt.restore_tracker.required_seconds = contract.restore.for_seconds
                self._runtimes[contract.id] = rt
            else:
                runtime.trigger_tracker.required_seconds = contract.trigger.for_seconds
                runtime.restore_tracker.required_seconds = contract.restore.for_seconds

    def step(
        self,
        telemetry: SystemSnapshot | None = None,
        observations: list[ProcessObservation] | None = None,
        now: float | None = None,
    ) -> EngineCycle:
        """Run one full cycle: sample (unless injected), drive, cache."""
        with self._lock:
            live_telemetry = telemetry if telemetry is not None else self._monitor.sample()
            live_observations = (
                observations if observations is not None else self._process_sampler()
            )
            moment = now if now is not None else time.monotonic()
            evaluations = self.evaluate_snapshot(live_telemetry, live_observations, moment)
            self._latest_telemetry = live_telemetry
            self._latest_observations = list(live_observations)
            return EngineCycle(
                telemetry=live_telemetry,
                process_count=len(live_observations),
                evaluations=evaluations,
            )

    def evaluate_snapshot(
        self,
        telemetry: SystemSnapshot,
        observations: list[ProcessObservation],
        now: float,
    ) -> list[ContractEvaluation]:
        """Drive every contract one step. Caller must hold no assumptions."""
        return [self._drive(contract, telemetry, observations, now) for contract in self._contracts]

    async def run_forever(self) -> None:
        """Poll until ``shutdown()`` stops the loop. No lock held to sleep."""
        while True:
            with self._lock:
                running = self._running
            if not running:
                return
            self.step()
            await asyncio.sleep(self.poll_interval_seconds)

    def shutdown(self) -> list[str]:
        """Stop the loop and best-effort restore every ACTIVE contract."""
        with self._lock:
            self._running = False
            problems: list[str] = []
            now = time.monotonic()
            for contract in self._contracts:
                runtime = self._runtimes[contract.id]
                # ACTIVATING and RESTORING are synchronous transitions performed
                # while this same lock is held, so shutdown cannot observe them.
                if runtime.lifecycle is not LifecycleState.ACTIVE and not (
                    runtime.lifecycle is LifecycleState.ERROR and runtime.snapshots
                ):
                    continue
                error = self._settle_snapshots(contract, runtime, reason="engine shutdown", now=now)
                if error is not None:
                    problems.append(f"{contract.id}: {error}")
            self._events.record(ArcEventType.ENGINE_STOPPED, "ARC engine stopped")
            logger.info("ARC engine stopped")
            return problems

    def contract_statuses(self) -> list[ContractStatusView]:
        """Copies of every contract plus runtime state."""
        with self._lock:
            return [self._status_view(contract) for contract in self._contracts]

    def engine_status(self) -> EngineStatusView:
        """Copy of engine health."""
        with self._lock:
            active = sum(
                1
                for runtime in self._runtimes.values()
                if runtime.lifecycle is LifecycleState.ACTIVE
            )
            errored = sum(
                1
                for runtime in self._runtimes.values()
                if runtime.lifecycle is LifecycleState.ERROR
            )
            cg_caps = self._cgroup_manager.capabilities()
            return EngineStatusView(
                running=self._running,
                platform=self._capabilities.platform,
                enforcement_supported=self._capabilities.enforcement_supported,
                euid=self._capabilities.euid,
                privileged_hint=self._capabilities.privileged_hint,
                poll_interval_seconds=self.poll_interval_seconds,
                contract_count=len(self._contracts),
                active_contracts=active,
                error_contracts=errored,
                event_count=len(self._events),
                cgroup_available=cg_caps.available,
                cgroup_reason=cg_caps.reason,
            )

    def recent_events(self, limit: int = 100) -> list[ArcEvent]:
        """Newest-first event history slice."""
        return self._events.recent(limit)

    def latest_telemetry(self) -> SystemSnapshot | None:
        """Last sampled telemetry, or None before the first step."""
        with self._lock:
            return self._latest_telemetry

    def latest_observations(self) -> list[ProcessObservation]:
        """Copy of the last process snapshot."""
        with self._lock:
            return list(self._latest_observations)

    def managed_pids_by_contract(self) -> dict[int, list[str]]:
        """Map each currently managed PID to the active contract IDs applying to it."""
        with self._lock:
            result: dict[int, list[str]] = {}
            for contract in self._contracts:
                runtime = self._runtimes.get(contract.id)
                if runtime is not None and runtime.lifecycle is LifecycleState.ACTIVE:
                    for snap in runtime.snapshots:
                        result.setdefault(snap.identity.pid, []).append(contract.id)
            return result

    def _status_view(self, contract: Contract) -> ContractStatusView:
        runtime = self._runtimes[contract.id]
        evaluation = self._last_evaluation(contract, runtime)
        now_mono = time.monotonic()
        trigger_elapsed: float | None = None
        restore_elapsed: float | None = None
        if runtime.trigger_tracker.satisfied_since is not None:
            trigger_elapsed = runtime.trigger_tracker.elapsed(now_mono)
        if runtime.restore_tracker.satisfied_since is not None:
            restore_elapsed = runtime.restore_tracker.elapsed(now_mono)
        return ContractStatusView(
            contract=contract,
            lifecycle=runtime.lifecycle,
            outcome=runtime.last_outcome,
            matched_pids=list(runtime.matched_pids),
            active_identities=[snap.identity for snap in runtime.snapshots],
            trigger_raw=evaluation.trigger_raw if evaluation else None,
            trigger_satisfied=evaluation.trigger_satisfied if evaluation else None,
            restore_raw=runtime.last_restore_raw,
            restore_satisfied=runtime.last_restore_satisfied,
            activated_at=runtime.activated_at,
            last_error=runtime.last_error,
            trigger_elapsed_seconds=trigger_elapsed,
            restore_elapsed_seconds=restore_elapsed,
        )

    def _last_evaluation(
        self, contract: Contract, runtime: ContractRuntimeState
    ) -> ContractEvaluation | None:
        if runtime.last_outcome is None:
            return None
        return ContractEvaluation(contract_id=contract.id, outcome=runtime.last_outcome)

    def _drive(
        self,
        contract: Contract,
        telemetry: SystemSnapshot,
        observations: list[ProcessObservation],
        now: float,
    ) -> ContractEvaluation:
        runtime = self._runtimes[contract.id]
        if runtime.lifecycle is LifecycleState.ERROR:
            return ContractEvaluation(
                contract_id=contract.id,
                outcome=runtime.last_outcome or EvaluationOutcome.EVALUATION_ERROR,
                lifecycle=LifecycleState.ERROR,
                matched_pids=list(runtime.matched_pids),
                detail="error latched, awaiting manual reset or restart",
                error=runtime.last_error,
            )
        if runtime.lifecycle is LifecycleState.ACTIVE:
            return self._drive_active(contract, runtime, telemetry, observations, now)
        previous = runtime.last_outcome
        result = evaluate_contract(contract, telemetry, observations, runtime, now)
        result.lifecycle = runtime.lifecycle
        if result.outcome is EvaluationOutcome.WOULD_ACTIVATE:
            if self._adapter.enforcement_supported:
                return self._try_activate(contract, runtime, observations, now)
            self._emit_on_change(
                contract.id, previous, result, ArcEventType.CONTRACT_TRIGGER_PENDING
            )
            return result
        if result.outcome is EvaluationOutcome.TRIGGER_PENDING:
            self._emit_on_change(
                contract.id, previous, result, ArcEventType.CONTRACT_TRIGGER_PENDING
            )
        return result

    def _try_activate(
        self,
        contract: Contract,
        runtime: ContractRuntimeState,
        observations: list[ProcessObservation],
        now: float,
    ) -> ContractEvaluation:
        by_pid = {obs.pid: obs for obs in observations}
        matched = [by_pid[pid] for pid in runtime.matched_pids if pid in by_pid]
        conflicts = self._resource_conflicts(contract, [obs.pid for obs in matched])
        if conflicts:
            detail = "; ".join(conflicts)
            evaluation = ContractEvaluation(
                contract_id=contract.id,
                outcome=EvaluationOutcome.RESOURCE_CONFLICT,
                lifecycle=LifecycleState.INACTIVE,
                trigger_raw=True,
                trigger_satisfied=True,
                matched_pids=list(runtime.matched_pids),
                detail=f"activation deferred: {detail}",
            )
            self._emit_on_change(
                contract.id,
                runtime.last_outcome,
                evaluation,
                ArcEventType.CONTRACT_CONFLICT,
            )
            runtime.note_evaluated(EvaluationOutcome.RESOURCE_CONFLICT, now)
            return evaluation
        runtime.transition_to(LifecycleState.ACTIVATING)
        self._events.record(
            ArcEventType.CONTRACT_ACTIVATING,
            f"contract {contract.id} activating for pids {[obs.pid for obs in matched]}",
            contract_id=contract.id,
            details={"matched_pids": [obs.pid for obs in matched]},
        )
        try:
            result = activate_contract(
                contract, matched, self._adapter, cgroup_manager=self._cgroup_manager
            )
        except Exception as exc:
            logger.exception("contract %s activation crashed", contract.id)
            result = None
            crash = f"activation crashed: {exc}"
        if result is not None and result.ok:
            runtime.snapshots = list(result.snapshots)
            runtime.activated_at = time.time()
            runtime.transition_to(LifecycleState.ACTIVE)
            for snapshot in result.snapshots:
                self._events.record(
                    ArcEventType.RESOURCE_SNAPSHOT_CAPTURED,
                    f"snapshot captured for pid {snapshot.identity.pid}",
                    contract_id=contract.id,
                    pid=snapshot.identity.pid,
                    details={
                        "create_time": snapshot.identity.create_time,
                        "prior_nice": snapshot.nice,
                        "prior_affinity": snapshot.affinity,
                        "prior_stopped": snapshot.stopped,
                        "prior_cpu_quota": snapshot.cpu_quota,
                    },
                )
            for op in result.applied:
                self._events.record(
                    ArcEventType.RESOURCE_ACTION_APPLIED,
                    f"{op.kind}={op.requested} applied to pid {op.pid}",
                    contract_id=contract.id,
                    pid=op.pid,
                    details={
                        "action_index": op.action_index,
                        "kind": op.kind,
                        "previous": str(op.previous),
                        "requested": op.requested,
                    },
                )
            self._events.record(
                ArcEventType.CONTRACT_ACTIVATED,
                f"contract {contract.id} active on {len(result.snapshots)} process(es)",
                contract_id=contract.id,
                details={
                    "target_count": len(result.snapshots),
                    "pids": [snapshot.identity.pid for snapshot in result.snapshots],
                },
            )
            runtime.note_evaluated(EvaluationOutcome.ACTIVATED, now)
            return ContractEvaluation(
                contract_id=contract.id,
                outcome=EvaluationOutcome.ACTIVATED,
                lifecycle=LifecycleState.ACTIVE,
                trigger_raw=True,
                trigger_satisfied=True,
                matched_pids=list(runtime.matched_pids),
                detail=f"enforced on {len(result.snapshots)} process(es)",
            )
        if result is None:
            error = crash
            rollback_errors: list[str] = []
        else:
            error = result.failure.error if result.failure else "activation failed"
            rollback_errors = result.failure.rollback_errors if result.failure else []
            if rollback_errors:
                runtime.snapshots = list(result.snapshots)
        runtime.transition_to(LifecycleState.ERROR)
        runtime.last_error = error
        self._events.record(
            ArcEventType.ENFORCEMENT_FAILED,
            f"contract {contract.id} activation failed: {error}",
            severity="error",
            contract_id=contract.id,
            details={"error": error, "rollback_errors": rollback_errors},
        )
        if rollback_errors:
            self._events.record(
                ArcEventType.ROLLBACK_FAILED,
                f"contract {contract.id} rollback incomplete: {'; '.join(rollback_errors)}",
                severity="error",
                contract_id=contract.id,
            )
        else:
            self._events.record(
                ArcEventType.ROLLBACK_COMPLETED,
                f"contract {contract.id} rolled back cleanly",
                contract_id=contract.id,
            )
        runtime.note_evaluated(EvaluationOutcome.ACTIVATION_ERROR, now)
        return ContractEvaluation(
            contract_id=contract.id,
            outcome=EvaluationOutcome.ACTIVATION_ERROR,
            lifecycle=LifecycleState.ERROR,
            matched_pids=list(runtime.matched_pids),
            detail=error,
            error=error,
        )

    def _resource_conflicts(self, candidate: Contract, pids: list[int]) -> list[str]:
        """Describe active resource owners that block a candidate activation.

        Ownership is per process lifetime and resource dimension. The engine lock
        serializes this check with activation and restoration, so a resource is
        claimed before another contract can mutate it and released only after
        restoration completes or the process lifetime is retired.
        """
        wanted = {_action_resource(action.type) for action in candidate.actions}
        pid_set = set(pids)
        conflicts: list[str] = []
        contract_by_id = {contract.id: contract for contract in self._contracts}
        for owner_id, owner_runtime in self._runtimes.items():
            if owner_id == candidate.id or owner_runtime.lifecycle not in (
                LifecycleState.ACTIVE,
                LifecycleState.RESTORING,
            ):
                continue
            owner = contract_by_id.get(owner_id)
            if owner is None:
                continue
            overlap = wanted & {_action_resource(action.type) for action in owner.actions}
            if not overlap:
                continue
            owned_pids = {snapshot.identity.pid for snapshot in owner_runtime.snapshots}
            for pid in sorted(pid_set & owned_pids):
                for resource in sorted(overlap):
                    conflicts.append(f"pid {pid} {resource} is owned by contract {owner_id}")
        return conflicts

    def _drive_active(
        self,
        contract: Contract,
        runtime: ContractRuntimeState,
        telemetry: SystemSnapshot,
        observations: list[ProcessObservation],
        now: float,
    ) -> ContractEvaluation:
        matched = resolve_process_target(contract.target, observations)
        runtime.matched_pids = [obs.pid for obs in matched]
        live, _, stale, unchecked = self._check_snapshots(runtime.snapshots)
        if stale or unchecked or not live:
            error = self._settle_snapshots(contract, runtime, reason="targets changed", now=now)
            if error is None:
                runtime.note_evaluated(EvaluationOutcome.RESTORED, now)
                return ContractEvaluation(
                    contract_id=contract.id,
                    outcome=EvaluationOutcome.RESTORED,
                    lifecycle=LifecycleState.INACTIVE,
                    matched_pids=list(runtime.matched_pids),
                    detail="activation retired with nothing left to restore",
                )
            runtime.note_evaluated(EvaluationOutcome.RESTORATION_ERROR, now)
            return ContractEvaluation(
                contract_id=contract.id,
                outcome=EvaluationOutcome.RESTORATION_ERROR,
                lifecycle=LifecycleState.ERROR,
                matched_pids=list(runtime.matched_pids),
                detail=error,
                error=error,
            )
        restore = evaluate_restore(contract, telemetry, matched, runtime, now)
        if not restore.satisfied:
            evaluation = ContractEvaluation(
                contract_id=contract.id,
                outcome=EvaluationOutcome.STILL_ACTIVE,
                lifecycle=LifecycleState.ACTIVE,
                matched_pids=list(runtime.matched_pids),
                restore_raw=restore.raw,
                restore_satisfied=False,
                detail=(
                    f"restore pending ({restore.elapsed_seconds:.1f}s of "
                    f"{restore.required_seconds:.1f}s)"
                ),
            )
            self._emit_on_change(
                contract.id, runtime.last_outcome, evaluation, ArcEventType.RESTORE_PENDING
            )
            runtime.note_evaluated(EvaluationOutcome.STILL_ACTIVE, now)
            return evaluation
        error = self._settle_snapshots(contract, runtime, reason="restore satisfied", now=now)
        if error is None:
            runtime.note_evaluated(EvaluationOutcome.RESTORED, now)
            return ContractEvaluation(
                contract_id=contract.id,
                outcome=EvaluationOutcome.RESTORED,
                lifecycle=LifecycleState.INACTIVE,
                matched_pids=list(runtime.matched_pids),
                restore_raw=True,
                restore_satisfied=True,
                detail="exact prior state restored and verified",
            )
        runtime.note_evaluated(EvaluationOutcome.RESTORATION_ERROR, now)
        return ContractEvaluation(
            contract_id=contract.id,
            outcome=EvaluationOutcome.RESTORATION_ERROR,
            lifecycle=LifecycleState.ERROR,
            matched_pids=list(runtime.matched_pids),
            detail=error,
            error=error,
        )

    def _settle_snapshots(
        self,
        contract: Contract,
        runtime: ContractRuntimeState,
        reason: str,
        now: float,
    ) -> str | None:
        """Restore live snapshots, retire exits, fail on stale identities."""
        live, gone, stale, unchecked = self._check_snapshots(runtime.snapshots)
        for pid in gone:
            self._events.record(
                ArcEventType.TARGET_DISAPPEARED,
                f"target pid {pid} exited while contract {contract.id} active",
                contract_id=contract.id,
                pid=pid,
            )
        if stale or unchecked:
            self._fail_stale_restore(contract, runtime, live, stale, unchecked, now)
            return runtime.last_error or "identity verification failed"
        if not live:
            runtime.snapshots = []
            runtime.clear_activation()
            runtime.last_error = None
            runtime.transition_to(LifecycleState.RESTORING)
            runtime.transition_to(LifecycleState.INACTIVE)
            self._events.record(
                ArcEventType.CONTRACT_RESTORING,
                f"contract {contract.id} restoring ({reason})",
                contract_id=contract.id,
            )
            self._events.record(
                ArcEventType.CONTRACT_RESTORED,
                f"contract {contract.id} retired with nothing to restore",
                contract_id=contract.id,
            )
            return None
        return self._restore_active(contract, runtime, live, reason=reason)

    def _check_snapshots(
        self, snapshots: list[ResourceSnapshot]
    ) -> tuple[list[ResourceSnapshot], list[int], list[int], list[str]]:
        """Sort snapshots into live, exited, reused-PID, and unverifiable."""
        live: list[ResourceSnapshot] = []
        gone: list[int] = []
        stale: list[int] = []
        unchecked: list[str] = []
        for snapshot in snapshots:
            pid = snapshot.identity.pid
            try:
                current = self._adapter.get_identity(pid)
            except ProcessNotFoundError:
                gone.append(pid)
                continue
            except ResourceControlError as exc:
                unchecked.append(f"pid {pid}: {exc.detail}")
                continue
            if current.create_time != snapshot.identity.create_time:
                logger.error(
                    "pid %s reused by a new process lifetime, refusing restoration",
                    pid,
                )
                stale.append(pid)
            else:
                live.append(snapshot)
        return live, gone, stale, unchecked

    def _fail_stale_restore(
        self,
        contract: Contract,
        runtime: ContractRuntimeState,
        live: list[ResourceSnapshot],
        stale: list[int],
        unchecked: list[str],
        now: float,
    ) -> ContractEvaluation:
        """Restore what is still safe, then ERROR on the unverifiable rest."""
        runtime.transition_to(LifecycleState.RESTORING)
        self._events.record(
            ArcEventType.CONTRACT_RESTORING,
            f"contract {contract.id} restoring (identity check failed)",
            contract_id=contract.id,
        )
        restored_note = "no live snapshots to restore"
        if live:
            try:
                result = restore_snapshots(live, self._adapter, cgroup_manager=self._cgroup_manager)
            except Exception as exc:
                logger.exception("contract %s restoration crashed", contract.id)
                result = None
                crash = f"restoration crashed: {exc}"
            if result is not None:
                for entry_pid in result.restored:
                    self._events.record(
                        ArcEventType.RESOURCE_RESTORED,
                        f"pid {entry_pid} restored to exact prior state",
                        contract_id=contract.id,
                        pid=entry_pid,
                    )
                restored_note = f"restored {len(result.restored)} of {len(live)} live snapshot(s)"
                if not result.ok:
                    restored_note += "; live restore had failures"
            else:
                restored_note = crash
        runtime.transition_to(LifecycleState.ERROR)
        problems = [f"reused PID left untouched: {stale}" if stale else ""]
        problems.extend(unchecked)
        joined = "; ".join(part for part in problems if part)
        error = f"identity verification failed ({restored_note}): {joined}"
        runtime.last_error = error
        self._events.record(
            ArcEventType.RESTORATION_FAILED,
            f"contract {contract.id}: {error}",
            severity="error",
            contract_id=contract.id,
        )
        runtime.note_evaluated(EvaluationOutcome.RESTORATION_ERROR, now)
        return ContractEvaluation(
            contract_id=contract.id,
            outcome=EvaluationOutcome.RESTORATION_ERROR,
            lifecycle=LifecycleState.ERROR,
            detail=error,
            error=error,
        )

    def _restore_active(
        self,
        contract: Contract,
        runtime: ContractRuntimeState,
        live_snapshots: list[ResourceSnapshot],
        reason: str,
    ) -> str | None:
        """Restore verified snapshots. Returns error text or None on success."""
        runtime.transition_to(LifecycleState.RESTORING)
        self._events.record(
            ArcEventType.CONTRACT_RESTORING,
            f"contract {contract.id} restoring ({reason})",
            contract_id=contract.id,
        )
        try:
            result = restore_snapshots(
                live_snapshots, self._adapter, cgroup_manager=self._cgroup_manager
            )
        except Exception as exc:
            logger.exception("contract %s restoration crashed", contract.id)
            runtime.transition_to(LifecycleState.ERROR)
            error = f"restoration crashed: {exc}"
            runtime.last_error = error
            self._events.record(
                ArcEventType.RESTORATION_FAILED,
                f"contract {contract.id}: {error}",
                severity="error",
                contract_id=contract.id,
            )
            return error
        for entry_pid in result.restored:
            self._events.record(
                ArcEventType.RESOURCE_RESTORED,
                f"pid {entry_pid} restored to exact prior state",
                contract_id=contract.id,
                pid=entry_pid,
            )
        if result.ok:
            runtime.clear_activation()
            runtime.last_error = None
            runtime.transition_to(LifecycleState.INACTIVE)
            self._events.record(
                ArcEventType.CONTRACT_RESTORED,
                f"contract {contract.id} restored, back to inactive",
                contract_id=contract.id,
            )
            return None
        problems = [
            f"pid {entry.pid} {entry.status}: {entry.detail}"
            for entry in result.entries
            if entry.status in ("failed", "stale")
        ]
        runtime.transition_to(LifecycleState.ERROR)
        error = f"restoration incomplete: {'; '.join(problems)}"
        runtime.last_error = error
        self._events.record(
            ArcEventType.RESTORATION_FAILED,
            f"contract {contract.id}: {error}",
            severity="error",
            contract_id=contract.id,
        )
        return error

    def _emit_on_change(
        self,
        contract_id: str,
        previous: EvaluationOutcome | None,
        evaluation: ContractEvaluation,
        event_type: ArcEventType,
    ) -> None:
        if previous != evaluation.outcome:
            message = f"contract {contract_id}: {evaluation.detail}"
            self._events.record(event_type, message, contract_id=contract_id)
        logger.debug("contract %s: %s", contract_id, evaluation.detail)
