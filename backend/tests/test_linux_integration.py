"""Narrow Linux-only smoke test on a spawned child process.

Skipped everywhere else. Never touches the pytest runner's own nice
value or affinity. Restores everything it changes, then terminates the
child in a finally block.
"""

import subprocess
import sys

import pytest

from arc.linux.psutil_adapter import LinuxResourceAdapter
from arc.linux.resources import ResourcePermissionError

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="requires Linux")


def test_real_adapter_roundtrip_on_child_process() -> None:
    """Get, set, verify, and restore nice plus affinity on a child."""
    adapter = LinuxResourceAdapter()
    assert adapter.enforcement_supported is True
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        original_nice = adapter.get_nice(child.pid)
        original_affinity = adapter.get_affinity(child.pid)
        assert original_affinity, "child must report a non-empty affinity"

        first = adapter.get_identity(child.pid)
        assert first.pid == child.pid
        assert adapter.get_identity(child.pid).create_time == first.create_time

        raised_nice = min(original_nice + 5, 19)
        adapter.set_nice(child.pid, raised_nice)
        assert adapter.get_nice(child.pid) == raised_nice

        narrowed = (original_affinity[0],)
        adapter.set_affinity(child.pid, list(narrowed))
        assert adapter.get_affinity(child.pid) == narrowed
        adapter.set_affinity(child.pid, list(original_affinity))
        assert adapter.get_affinity(child.pid) == tuple(sorted(original_affinity))

        try:
            adapter.set_nice(child.pid, original_nice)
        except ResourcePermissionError:
            pytest.skip("lowering nice back needs privilege on this host")
        assert adapter.get_nice(child.pid) == original_nice
    finally:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=10)
