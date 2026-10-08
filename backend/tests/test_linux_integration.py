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

from arc.linux.psutil_adapter import LinuxResourceAdapter
from arc.linux.resources import ResourcePermissionError

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
