"""Real, read-only system telemetry built on psutil.

CPU sampling note: ``psutil.cpu_percent(interval=None)`` compares
against the previous call, so the first sample after process start is
meaningless (usually 0.0). ``SystemMonitor`` primes the sampler on
creation and documents this. Sampling is always non-blocking so HTTP
requests never wait on a measurement interval.
"""

import logging
import time
from dataclasses import dataclass

import psutil

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SystemSnapshot:
    """Point-in-time, read-only view of system state."""

    cpu_percent: float
    memory_percent: float
    cpu_count: int
    timestamp: float
    cpu_per_core_percent: tuple[float, ...] = ()


def _clamp_percent(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def sample_system() -> SystemSnapshot:
    """Take one non-blocking system snapshot. Read-only."""
    try:
        cpu = _clamp_percent(psutil.cpu_percent(interval=None))
        per_core = tuple(
            _clamp_percent(value) for value in psutil.cpu_percent(interval=None, percpu=True)
        )
        memory = _clamp_percent(psutil.virtual_memory().percent)
        count = psutil.cpu_count(logical=True) or 1
    except Exception as exc:
        logger.warning("system sampling failed: %s", exc)
        raise
    return SystemSnapshot(
        cpu_percent=cpu,
        memory_percent=memory,
        cpu_count=int(count),
        timestamp=time.time(),
        cpu_per_core_percent=per_core,
    )


class SystemMonitor:
    """Continuously usable system sampler with primed CPU measurement."""

    def __init__(self) -> None:
        try:
            psutil.cpu_percent(interval=None)
            psutil.cpu_percent(interval=None, percpu=True)
        except Exception as exc:
            logger.warning("system monitor priming failed: %s", exc)

    def sample(self) -> SystemSnapshot:
        """Take one non-blocking snapshot. Read-only, never mutates the OS."""
        return sample_system()
