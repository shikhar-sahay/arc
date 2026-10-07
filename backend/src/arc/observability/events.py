"""Small in-memory ARC event history.

Events record meaningful transitions only: lifecycle changes, applied
and restored resources, failures. The engine emits on change, never
every poll. History is bounded (latest 500) with no database and no
event bus.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

MAX_EVENTS = 500


class ArcEventType(StrEnum):
    """Stable event categories for logs, API, and UI."""

    ENGINE_STARTED = "engine_started"
    ENGINE_STOPPED = "engine_stopped"
    CONTRACT_TRIGGER_PENDING = "contract_trigger_pending"
    CONTRACT_ACTIVATING = "contract_activating"
    RESOURCE_SNAPSHOT_CAPTURED = "resource_snapshot_captured"
    RESOURCE_ACTION_APPLIED = "resource_action_applied"
    CONTRACT_ACTIVATED = "contract_activated"
    RESTORE_PENDING = "restore_pending"
    CONTRACT_RESTORING = "contract_restoring"
    RESOURCE_RESTORED = "resource_restored"
    CONTRACT_RESTORED = "contract_restored"
    TARGET_DISAPPEARED = "target_disappeared"
    ENFORCEMENT_FAILED = "enforcement_failed"
    ROLLBACK_COMPLETED = "rollback_completed"
    ROLLBACK_FAILED = "rollback_failed"
    RESTORATION_FAILED = "restoration_failed"
    EVALUATION_ERROR = "evaluation_error"


@dataclass(frozen=True)
class ArcEvent:
    """One recorded transition."""

    seq: int
    timestamp: float
    type: ArcEventType
    severity: str
    contract_id: str | None
    pid: int | None
    message: str
    details: dict[str, object] = field(default_factory=dict)


class EventLog:
    """Thread-safe bounded history, newest kept, copies handed out."""

    def __init__(self, maxlen: int = MAX_EVENTS) -> None:
        self._events: deque[ArcEvent] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._seq = 0

    def record(
        self,
        type: ArcEventType,
        message: str,
        severity: str = "info",
        contract_id: str | None = None,
        pid: int | None = None,
        details: dict[str, object] | None = None,
    ) -> ArcEvent:
        """Append one event and return it."""
        with self._lock:
            self._seq += 1
            event = ArcEvent(
                seq=self._seq,
                timestamp=time.time(),
                type=type,
                severity=severity,
                contract_id=contract_id,
                pid=pid,
                message=message,
                details=dict(details or {}),
            )
            self._events.append(event)
            return event

    def recent(self, limit: int = 100) -> list[ArcEvent]:
        """Newest first, up to ``limit`` entries. Returns copies."""
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._lock:
            return list(reversed(list(self._events)[-limit:]))

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)
