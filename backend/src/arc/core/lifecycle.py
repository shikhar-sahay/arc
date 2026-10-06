"""Contract lifecycle states and per-contract runtime state.

Configuration (the YAML contract) is declarative and persistent. Runtime
state (duration timers, matched PIDs, evaluation results) is transient,
kept in memory, and never written back into YAML files.

Because enforcement is not implemented yet, the read-only evaluator
reports preview outcomes such as ``WOULD_ACTIVATE`` and leaves the
lifecycle in ``INACTIVE``. The authoritative ``ACTIVE`` transition will
be wired to successful enforcement in a later pass. Preview results must
never be reported as successful enforcement.
"""

import time
from dataclasses import dataclass, field
from enum import StrEnum


class LifecycleState(StrEnum):
    """Authoritative enforcement lifecycle for a contract."""

    INACTIVE = "inactive"
    ACTIVATING = "activating"
    ACTIVE = "active"
    RESTORING = "restoring"
    ERROR = "error"


class EvaluationOutcome(StrEnum):
    """Read-only observation result for one evaluation cycle."""

    DISABLED = "disabled"
    TARGET_NOT_FOUND = "target_not_found"
    TRIGGER_PENDING = "trigger_pending"
    WOULD_ACTIVATE = "would_activate"
    EVALUATION_ERROR = "evaluation_error"


class DurationTracker:
    """Tracks continuous satisfaction of a condition on a monotonic clock.

    The clock value is passed in by the caller so tests can advance time
    deterministically without sleeping. Use ``time.monotonic()`` at the
    call site in production code.
    """

    def __init__(self, required_seconds: float = 0) -> None:
        if required_seconds < 0:
            raise ValueError("required_seconds must be non-negative")
        self.required_seconds = required_seconds
        self.satisfied_since: float | None = None

    def update(self, observed: bool, now: float) -> bool:
        """Record one sample. Return True once duration is satisfied."""
        if not observed:
            self.satisfied_since = None
            return False
        if self.required_seconds <= 0:
            return True
        if self.satisfied_since is None:
            self.satisfied_since = now
        return (now - self.satisfied_since) >= self.required_seconds

    def elapsed(self, now: float) -> float:
        """Seconds of continuous satisfaction up to ``now``."""
        if self.satisfied_since is None:
            return 0.0
        return max(0.0, now - self.satisfied_since)

    def reset(self) -> None:
        """Forget any partial duration progress."""
        self.satisfied_since = None


@dataclass
class ContractRuntimeState:
    """Transient per-contract state owned by the evaluation engine."""

    contract_id: str
    lifecycle: LifecycleState = LifecycleState.INACTIVE
    trigger_tracker: DurationTracker = field(default_factory=DurationTracker)
    restore_tracker: DurationTracker = field(default_factory=DurationTracker)
    last_outcome: EvaluationOutcome | None = None
    matched_pids: list[int] = field(default_factory=list)
    last_error: str | None = None
    last_evaluated_monotonic: float | None = None

    def note_evaluated(self, outcome: EvaluationOutcome, now: float | None = None) -> None:
        """Record that an evaluation cycle completed for this contract."""
        self.last_outcome = outcome
        self.last_evaluated_monotonic = now if now is not None else time.monotonic()
