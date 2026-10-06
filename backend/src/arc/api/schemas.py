"""Typed API models for the ARC read-only interface.

Domain models (contracts, snapshots, evaluations) are reused directly
where they already serialize cleanly. The response wrappers below add
only transport-level shape such as counts and load errors.
"""

from pydantic import BaseModel, Field

from arc.contracts.models import Contract
from arc.core.lifecycle import EvaluationOutcome
from arc.monitoring.processes import ProcessObservation
from arc.monitoring.system import SystemSnapshot


class HealthResponse(BaseModel):
    """Typed response for GET /api/health."""

    app: str
    status: str
    platform: str


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

    @classmethod
    def from_observation(cls, observation: ProcessObservation) -> "ProcessResponse":
        """Build a response from a domain observation."""
        return cls(
            pid=observation.pid,
            name=observation.name,
            cmdline=observation.cmdline,
            cpu_percent=observation.cpu_percent,
            memory_percent=observation.memory_percent,
        )


class ProcessListResponse(BaseModel):
    """Bounded process snapshot for GET /api/processes."""

    processes: list[ProcessResponse]
    count: int
    limit: int
    total_observed: int


class ContractStatus(BaseModel):
    """A loaded contract plus its latest read-only evaluation."""

    contract: Contract
    outcome: EvaluationOutcome | None = None
    matched_pids: list[int] = Field(default_factory=list)
    trigger_raw: bool | None = None
    trigger_satisfied: bool | None = None
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
