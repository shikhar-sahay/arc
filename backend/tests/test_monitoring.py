"""Tests for read-only monitoring built on real psutil."""

import os

import psutil
import pytest

from arc.monitoring.processes import sample_processes
from arc.monitoring.system import SystemMonitor, sample_system


def test_system_snapshot_is_structurally_valid() -> None:
    """Real telemetry returns values in sane ranges, not exact numbers."""
    snapshot = sample_system()

    assert 0.0 <= snapshot.cpu_percent <= 100.0
    assert 0.0 <= snapshot.memory_percent <= 100.0
    assert snapshot.cpu_count >= 1
    assert snapshot.timestamp > 0


def test_system_monitor_samples_without_blocking() -> None:
    """The primed monitor produces a second valid snapshot."""
    monitor = SystemMonitor()

    snapshot = monitor.sample()

    assert 0.0 <= snapshot.cpu_percent <= 100.0
    assert snapshot.cpu_count >= 1


def test_process_snapshot_contains_current_process() -> None:
    """Enumeration sees at least the test process itself."""
    observations = sample_processes()
    pids = [obs.pid for obs in observations]

    assert os.getpid() in pids
    assert pids == sorted(pids)


def test_dead_or_denied_processes_do_not_crash_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One bad process entry cannot abort the whole monitoring cycle."""

    class Gone:
        @property
        def info(self) -> dict[str, object]:
            raise psutil.NoSuchProcess(pid=1)

    class Denied:
        @property
        def info(self) -> dict[str, object]:
            raise psutil.AccessDenied(pid=2)

    class Fine:
        def __init__(self) -> None:
            self.info = {"pid": 3, "name": "fine", "cmdline": ["fine"]}

        def cpu_percent(self, interval: object = None) -> float:
            return 1.0

        def memory_percent(self) -> float:
            return 2.0

    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [Gone(), Denied(), Fine()])

    observations = sample_processes()

    assert [obs.pid for obs in observations] == [3]
    assert observations[0].name == "fine"
