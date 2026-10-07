"""Contract lifecycle states and per-contract runtime state.

Configuration (the YAML contract) is declarative and persistent. Runtime
state (duration timers, matched PIDs, snapshots, lifecycle, evaluation
results) is transient, kept in memory, and never written back into YAML
files.

Lifecycle moves only through ``transition_to``, which enforces the
allowed map. Satisfied triggers on platforms without enforcement yield
the ``WOULD_ACTIVATE`` preview while the lifecycle stays ``INACTIVE``.
Preview results must never be reported as successful enforcement.
"""

import time
from dataclasses import dataclass, field
from enum import StrEnum

from arc.linux.resources import ResourceSnapshot


class LifecycleTransitionError(Exception):
    """An illegal lifecycle move was attempted."""


class LifecycleState(StrEnum):
    """Authoritative enforcement lifecycle for a contract."""

    INACTIVE = "inactive"
    ACTIVATING = "activating"
    ACTIVE = "active"
    RESTORING = "restoring"
    ERROR = "error"


_ALLOWED_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.INACTIVE: frozenset({LifecycleState.ACTIVATING, LifecycleState.ERROR}),
    LifecycleState.ACTIVATING: frozenset({LifecycleState.ACTIVE, LifecycleState.ERROR}),
    LifecycleState.ACTIVE: frozenset({LifecycleState.RESTORING, LifecycleState.ERROR}),
    LifecycleState.RESTORING: frozenset(
        {LifecycleState.INACTIVE, LifecycleState.ACTIVE, LifecycleState.ERROR}
    ),
    LifecycleState.ERROR: frozenset({LifecycleState.INACTIVE}),
}


class EvaluationOutcome(StrEnum):
    """Per-cycle observation result for one contract."""

    DISABLED = "disabled"
    TARGET_NOT_FOUND = "target_not_found"
    TRIGGER_PENDING = "trigger_pending"
    WOULD_ACTIVATE = "would_activate"
    ACTIVATED = "activated"
    STILL_ACTIVE = "still_active"
    RESTORED = "restored"
    ACTIVATION_ERROR = "activation_error"
    RESTORATION_ERROR = "restoration_error"
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
    """Transient per-contract state owned by the runtime engine."""

    contract_id: str
    lifecycle: LifecycleState = LifecycleState.INACTIVE
    trigger_tracker: DurationTracker = field(default_factory=DurationTracker)
    restore_tracker: DurationTracker = field(default_factory=DurationTracker)
    last_outcome: EvaluationOutcome | None = None
    matched_pids: list[int] = field(default_factory=list)
    snapshots: list[ResourceSnapshot] = field(default_factory=list)
    activated_at: float | None = None
    last_restore_raw: bool | None = None
    last_restore_satisfied: bool | None = None
    last_error: str | None = None
    last_evaluated_monotonic: float | None = None

    def transition_to(self, new_state: LifecycleState) -> None:
        """Move lifecycle, rejecting anything outside the allowed map."""
        allowed = _ALLOWED_TRANSITIONS[self.lifecycle]
        if new_state not in allowed and new_state is not self.lifecycle:
            raise LifecycleTransitionError(
                f"contract {self.contract_id}: "
                f"{self.lifecycle.value} -> {new_state.value} is not allowed"
            )
        self.lifecycle = new_state

    def note_evaluated(self, outcome: EvaluationOutcome, now: float | None = None) -> None:
        """Record that an evaluation cycle completed for this contract."""
        self.last_outcome = outcome
        self.last_evaluated_monotonic = now if now is not None else time.monotonic()

    def clear_activation(self) -> None:
        """Drop activation-specific state after a completed episode."""
        self.snapshots = []
        self.activated_at = None
        self.last_restore_raw = None
        self.last_restore_satisfied = None
        self.trigger_tracker.reset()
        self.restore_tracker.reset()

    def reset_error(self) -> None:
        """Manual recovery path: ERROR back to INACTIVE with timers cleared."""
        self.lifecycle = LifecycleState.INACTIVE
        self.last_error = None
        self.clear_activation()
