"""Narrow Linux-only smoke test on a spawned child process.

Skipped everywhere else. Never touches the pytest runner's own nice
value or affinity. Restores everything it changes, then terminates the
child in a finally block.
"""

import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from arc.contracts.models import Contract
from arc.core.engine import ObservationEngine
from arc.core.lifecycle import LifecycleState
from arc.linux.psutil_adapter import LinuxResourceAdapter
from arc.linux.resources import ResourcePermissionError
from arc.monitoring.processes import ProcessObservation
from arc.monitoring.system import SystemSnapshot

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="requires Linux")


@contextmanager
def controlled_child() -> Iterator[subprocess.Popen[bytes]]:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        yield child
    finally:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=10)


def test_real_adapter_affinity_roundtrip_on_child_process() -> None:
    """Constrain and exactly restore affinity on a controlled child."""
    adapter = LinuxResourceAdapter()
    assert adapter.enforcement_supported is True
    with controlled_child() as child:
        original_affinity = adapter.get_affinity(child.pid)
        assert original_affinity, "child must report a non-empty affinity"
        identity = adapter.get_identity(child.pid)

        narrowed = (original_affinity[0],)
        adapter.set_affinity(child.pid, list(narrowed))
        assert adapter.get_affinity(child.pid) == narrowed
        adapter.set_affinity(child.pid, list(original_affinity))
        assert adapter.get_affinity(child.pid) == tuple(sorted(original_affinity))
        assert adapter.get_identity(child.pid).create_time == identity.create_time


def test_real_adapter_signal_roundtrip_on_child_process() -> None:
    """SIGSTOP and SIGCONT a controlled child, with read-back verification."""
    adapter = LinuxResourceAdapter()
    with controlled_child() as child:
        assert adapter.is_stopped(child.pid) is False
        adapter.suspend_process(child.pid)
        assert adapter.is_stopped(child.pid) is True
        adapter.resume_process(child.pid)
        assert adapter.is_stopped(child.pid) is False


def test_real_adapter_nice_roundtrip_on_child_process() -> None:
    """Raise nice and restore it where the current user has permission."""
    adapter = LinuxResourceAdapter()
    with controlled_child() as child:
        original_nice = adapter.get_nice(child.pid)
        raised_nice = min(original_nice + 5, 19)
        adapter.set_nice(child.pid, raised_nice)
        assert adapter.get_nice(child.pid) == raised_nice
        try:
            adapter.set_nice(child.pid, original_nice)
        except ResourcePermissionError:
            pytest.skip("lowering nice back needs privilege on this host")
        assert adapter.get_nice(child.pid) == original_nice


def test_engine_repeats_affinity_enforcement_and_exact_restoration() -> None:
    """Run three complete engine cycles against one real Linux child."""
    adapter = LinuxResourceAdapter()
    with controlled_child() as child:
        original = adapter.get_affinity(child.pid)
        if len(original) < 2:
            pytest.skip("affinity cycle needs at least two available CPUs")
        contract = Contract.model_validate(
            {
                "version": 1,
                "id": "linux-affinity-cycle",
                "name": "Linux affinity cycle",
                "enabled": True,
                "target": {
                    "type": "process",
                    "match": {"executable": "python", "command_contains": "time.sleep(120)"},
                },
                "trigger": {
                    "metric": "system.cpu.percent",
                    "operator": "gt",
                    "value": 20,
                    "for_seconds": 0,
                },
                "actions": [{"type": "cpu_affinity", "cpus": [original[0]]}],
                "restore": {
                    "metric": "system.cpu.percent",
                    "operator": "lt",
                    "value": 10,
                    "for_seconds": 0,
                },
            }
        )
        engine = ObservationEngine([contract], resource_adapter=adapter)
        observation = ProcessObservation(
            pid=child.pid,
            name="python",
            cmdline="python -c import time; time.sleep(120)",
            cpu_percent=0.0,
            memory_percent=0.0,
        )

        for cycle in range(3):
            high = SystemSnapshot(50.0, 10.0, len(original), float(cycle * 2))
            engine.step(high, [observation], now=float(cycle * 2))
            assert engine.runtime_for(contract.id).lifecycle is LifecycleState.ACTIVE
            assert adapter.get_affinity(child.pid) == (original[0],)

            low = SystemSnapshot(0.2, 10.0, len(original), float(cycle * 2 + 1))
            engine.step(low, [observation], now=float(cycle * 2 + 1))
            assert engine.runtime_for(contract.id).lifecycle is LifecycleState.INACTIVE
            assert adapter.get_affinity(child.pid) == original
