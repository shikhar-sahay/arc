"""Authoritative Adaptive Resource Contract domain model.

This module defines the initial, intentionally constrained ARC contract
schema. Contracts are declarative configuration loaded from YAML. Runtime
state (matched PIDs, duration timers, evaluation results) lives in
``arc.core.lifecycle`` and is never written back into YAML files.

Action models describe intent. Execution lives behind the
``arc.linux`` adapter boundary and the enforcement service.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_ID_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"

NICE_MIN = -20
NICE_MAX = 19


class MetricName(StrEnum):
    """Supported condition metrics for the initial schema."""

    SYSTEM_CPU_PERCENT = "system.cpu.percent"
    SYSTEM_MEMORY_PERCENT = "system.memory.percent"
    TARGET_PROCESS_PRESENT = "target.process.present"


class NumericOperator(StrEnum):
    """Comparison operators for numeric metrics."""

    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EQ = "eq"
    NE = "ne"


class BooleanOperator(StrEnum):
    """Comparison operators for boolean metrics."""

    EQ = "eq"
    NE = "ne"


class ProcessMatch(BaseModel):
    """How to find a runtime process without persisting a PID.

    PIDs are ephemeral and may be reused, so contracts match on process
    metadata instead. When both fields are present, both must match.
    Matching is case sensitive and deterministic.
    """

    model_config = ConfigDict(extra="forbid")

    executable: str | None = Field(default=None, min_length=1)
    command_contains: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _require_at_least_one_criterion(self) -> "ProcessMatch":
        if self.executable is None and self.command_contains is None:
            raise ValueError("process match needs executable, command_contains, or both")
        return self


class ProcessTarget(BaseModel):
    """Process target. Other target types may be added later."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["process"] = "process"
    match: ProcessMatch


class Condition(BaseModel):
    """A single trigger or restoration condition.

    ``for_seconds`` requires the raw comparison to hold continuously for
    that long (measured on a monotonic clock) before the condition counts
    as satisfied. It defaults to 0, meaning a true comparison satisfies
    immediately. Separate trigger and restoration conditions allow
    hysteresis, for example activate above 75 percent and restore below
    55 percent, so the contract does not flap around one threshold.
    """

    model_config = ConfigDict(extra="forbid")

    metric: MetricName
    operator: str = Field(min_length=1)
    value: float | bool
    for_seconds: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _check_operator_and_value(self) -> "Condition":
        if self.metric in (MetricName.SYSTEM_CPU_PERCENT, MetricName.SYSTEM_MEMORY_PERCENT):
            try:
                NumericOperator(self.operator)
            except ValueError:
                raise ValueError(
                    f"metric {self.metric.value} needs a numeric operator "
                    "(gt, gte, lt, lte, eq, ne)"
                ) from None
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise ValueError(f"metric {self.metric.value} needs a numeric value")
            if not 0 <= float(self.value) <= 100:
                raise ValueError(f"metric {self.metric.value} needs a value in 0 to 100")
        else:
            try:
                BooleanOperator(self.operator)
            except ValueError:
                raise ValueError(
                    f"metric {self.metric.value} needs a boolean operator (eq, ne)"
                ) from None
            if not isinstance(self.value, bool):
                raise ValueError(f"metric {self.metric.value} needs a boolean value")
        return self


class NiceAction(BaseModel):
    """Adjust a process nice value (executed on Linux)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["nice"] = "nice"
    value: int = Field(ge=NICE_MIN, le=NICE_MAX)


class CpuAffinityAction(BaseModel):
    """Constrain process CPUs (executed on Linux)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["cpu_affinity"] = "cpu_affinity"
    cpus: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_cpus(self) -> "CpuAffinityAction":
        if any(not isinstance(cpu, int) or isinstance(cpu, bool) for cpu in self.cpus):
            raise ValueError("cpu_affinity cpus must be integers")
        if any(cpu < 0 for cpu in self.cpus):
            raise ValueError("cpu_affinity cpus must be non-negative")
        if len(set(self.cpus)) != len(self.cpus):
            raise ValueError("cpu_affinity cpus must not contain duplicates")
        return self


class SuspendAction(BaseModel):
    """Suspend a process with SIGSTOP (executed on Linux)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["suspend"] = "suspend"


class ResumeAction(BaseModel):
    """Resume a process with SIGCONT (executed on Linux)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["resume"] = "resume"


class CpuQuotaAction(BaseModel):
    """Intent to cap a process CPU share via cgroups v2 cpu.max.

    ``quota_percent`` maps to ``<quota> 100000`` in cpu.max, so 50.0
    means half of one CPU per period. Range is 1 to 100.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["cpu_quota"] = "cpu_quota"
    quota_percent: float = Field(ge=1, le=100)


Action = Annotated[
    NiceAction | CpuAffinityAction | SuspendAction | ResumeAction | CpuQuotaAction,
    Field(discriminator="type"),
]


class Contract(BaseModel):
    """An Adaptive Resource Contract: trigger, actions, restoration.

    The ``restore`` field is a restoration CONDITION (when the contract
    should stop applying). It is not a snapshot of resource state.
    Snapshots are captured at activation and restored exactly.
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    id: str = Field(pattern=CONTRACT_ID_PATTERN)
    name: str = Field(min_length=1)
    description: str | None = None
    enabled: bool = True
    target: ProcessTarget
    trigger: Condition
    actions: list[Action] = Field(min_length=1)
    restore: Condition
