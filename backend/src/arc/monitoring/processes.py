"""Real, read-only process observation and target resolution.

Processes can disappear between enumeration and inspection, and access
can be denied. A single inaccessible or dead process never aborts the
whole snapshot. Unavailable fields stay ``None`` instead of invented
values.
"""

import logging
from dataclasses import dataclass

import psutil

from arc.contracts.models import ProcessTarget

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessObservation:
    """Read-only view of one process at snapshot time."""

    pid: int
    name: str | None
    cmdline: str | None
    cpu_percent: float | None
    memory_percent: float | None


def _join_cmdline(parts: object) -> str | None:
    if not parts:
        return None
    if not isinstance(parts, (list, tuple)):
        return None
    text = " ".join(str(part) for part in parts).strip()
    return text or None


def sample_processes() -> list[ProcessObservation]:
    """Snapshot visible processes, sorted by PID. Read-only."""
    observations: list[ProcessObservation] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            info = proc.info
            pid = int(info.get("pid"))
            name = info.get("name")
            cmdline = _join_cmdline(info.get("cmdline"))
            try:
                cpu = proc.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                cpu = None
            try:
                memory = proc.memory_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                memory = None
            observations.append(
                ProcessObservation(
                    pid=pid,
                    name=str(name) if name else None,
                    cmdline=cmdline,
                    cpu_percent=float(cpu) if cpu is not None else None,
                    memory_percent=float(memory) if memory is not None else None,
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as exc:
            logger.warning("skipping process during snapshot: %s", exc)
            continue
    observations.sort(key=lambda obs: obs.pid)
    return observations


def resolve_process_target(
    target: ProcessTarget, observations: list[ProcessObservation]
) -> list[ProcessObservation]:
    """Return every process matching the target, sorted by PID.

    Matching is case sensitive: ``executable`` must equal the process
    name, and ``command_contains`` must appear in the joined command
    line. All matches are returned. The caller must not silently pick a
    single PID when several match.
    """
    wanted = target.match
    matched = [
        obs
        for obs in observations
        if (wanted.executable is None or obs.name == wanted.executable)
        and (
            wanted.command_contains is None
            or (obs.cmdline is not None and wanted.command_contains in obs.cmdline)
        )
    ]
    matched.sort(key=lambda obs: obs.pid)
    return matched
