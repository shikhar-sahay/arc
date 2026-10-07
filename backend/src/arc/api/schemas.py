"""Typed API models for the ARC interface.

Domain models (contracts, snapshots, evaluations) are reused directly
where they already serialize cleanly. The response wrappers below add
only transport-level shape such as counts and load errors.
"""

from pydantic import BaseModel, Field

from arc.contracts.models import Contract
from arc.core.lifecycle import EvaluationOutcome, LifecycleState
from arc.monitoring.processes import ProcessObservation
from arc.monitoring.system import SystemSnapshot
from arc.observability.events import ArcEvent, ArcEventType


class HealthResponse(BaseModel):
    """Liveness plus engine summary for GET /api/health."""

    app: str
    status: str
    platform: str
    engine_running: bool = False
    enforcement_supported: bool = False
    contract_count: int = 0
    active_contracts: int = 0
    error_contracts: int = 0


class EngineStatusResponse(BaseModel):
    """Full engine and capability report for GET /api/status."""

    running: bool
    platform: str
    enforcement_supported: bool
    euid: int | None = None
    privileged_hint: bool | None = None
    poll_interval_seconds: float
    contract_count: int
    active_contracts: int
    error_contracts: int
    event_count: int
    cgroup_available: bool = False
    cgroup_reason: str = ""


class SystemResponse(BaseModel):
    """Current read-only system telemetry for GET /api/system."""

    cpu_percent: float
    memory_percent: float
    cpu_count: int
    timestamp: float

    @classmethod
    def from_snapshot(cls, snapshot: SystemSnapshot) -> "SystemResponse":
        """Build a response from a domain snapshot."""
        return cls(
            cpu_percent=snapshot.cpu_percent,
            memory_percent=snapshot.memory_percent,
            cpu_count=snapshot.cpu_count,
            timestamp=snapshot.timestamp,
        )


class ProcessResponse(BaseModel):
    """One read-only process entry for GET /api/processes."""

    pid: int
    name: str | None
    cmdline: str | None
    cpu_percent: float | None
    memory_percent: float | None
    nice: int | None = None
    cpu_affinity: list[int] | None = None
    arc_managed: bool = False
    active_contract_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_observation(
        cls,
        observation: ProcessObservation,
        nice: int | None = None,
        cpu_affinity: list[int] | None = None,
        arc_managed: bool = False,
        active_contract_ids: list[str] | None = None,
    ) -> "ProcessResponse":
        """Build a response from a domain observation."""
        return cls(
            pid=observation.pid,
            name=observation.name,
            cmdline=observation.cmdline,
            cpu_percent=observation.cpu_percent,
            memory_percent=observation.memory_percent,
            nice=nice,
            cpu_affinity=cpu_affinity,
            arc_managed=arc_managed,
            active_contract_ids=active_contract_ids or [],
        )


class ProcessListResponse(BaseModel):
    """Bounded process snapshot for GET /api/processes."""

    processes: list[ProcessResponse]
    count: int
    limit: int
    total_observed: int


class TargetIdentityResponse(BaseModel):
    """A resolved target process identity for GET /api/contracts."""

    pid: int
    create_time: float
    name: str | None = None


class ContractStatus(BaseModel):
    """A loaded contract plus its live runtime state."""

    contract: Contract
    lifecycle: LifecycleState = LifecycleState.INACTIVE
    outcome: EvaluationOutcome | None = None
    matched_pids: list[int] = Field(default_factory=list)
    active_targets: list[TargetIdentityResponse] = Field(default_factory=list)
    trigger_raw: bool | None = None
    trigger_satisfied: bool | None = None
    restore_raw: bool | None = None
    restore_satisfied: bool | None = None
    activated_at: float | None = None
    detail: str = ""
    error: str | None = None


class ContractLoadIssue(BaseModel):
    """A contract file that failed to load, with the reason."""

    file: str
    error: str


class ContractListResponse(BaseModel):
    """Loaded contracts for GET /api/contracts."""

    contracts: list[ContractStatus]
    count: int
    load_errors: list[ContractLoadIssue] = Field(default_factory=list)


class EventResponse(BaseModel):
    """One ARC lifecycle event, newest first in listings."""

    seq: int
    timestamp: float
    type: ArcEventType
    severity: str
    contract_id: str | None = None
    pid: int | None = None
    message: str
    details: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_event(cls, event: ArcEvent) -> "EventResponse":
        """Build a response from a domain event."""
        return cls(
            seq=event.seq,
            timestamp=event.timestamp,
            type=event.type,
            severity=event.severity,
            contract_id=event.contract_id,
            pid=event.pid,
            message=event.message,
            details=event.details,
        )


class EventListResponse(BaseModel):
    """Bounded newest-first event history for GET /api/events."""

    events: list[EventResponse]
    count: int
    limit: int
