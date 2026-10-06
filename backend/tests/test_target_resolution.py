"""Tests for process target resolution."""

from arc.contracts.models import ProcessTarget
from arc.monitoring.processes import ProcessObservation, resolve_process_target


def _target(**match: str) -> ProcessTarget:
    return ProcessTarget.model_validate({"type": "process", "match": match})


OBSERVATIONS = [
    ProcessObservation(
        pid=300,
        name="python",
        cmdline="python demo_cpu_worker.py",
        cpu_percent=10.0,
        memory_percent=1.0,
    ),
    ProcessObservation(
        pid=100,
        name="python",
        cmdline="python other.py",
        cpu_percent=5.0,
        memory_percent=1.0,
    ),
    ProcessObservation(
        pid=200,
        name="nginx",
        cmdline="nginx -g daemon off",
        cpu_percent=1.0,
        memory_percent=0.5,
    ),
    ProcessObservation(pid=400, name="python", cmdline=None, cpu_percent=2.0, memory_percent=0.5),
]


def test_executable_name_match() -> None:
    """Processes match by executable name."""
    matched = resolve_process_target(_target(executable="python"), OBSERVATIONS)

    assert [obs.pid for obs in matched] == [100, 300, 400]


def test_command_substring_match() -> None:
    """Processes match by command line substring."""
    matched = resolve_process_target(_target(command_contains="demo_cpu_worker"), OBSERVATIONS)

    assert [obs.pid for obs in matched] == [300]


def test_both_constraints_must_match() -> None:
    """Executable and command substring combine as AND."""
    matched = resolve_process_target(
        _target(executable="python", command_contains="other.py"), OBSERVATIONS
    )

    assert [obs.pid for obs in matched] == [100]


def test_no_match_returns_empty() -> None:
    """Unknown workloads resolve to nothing, not to a guess."""
    matched = resolve_process_target(_target(executable="no-such-proc"), OBSERVATIONS)

    assert matched == []


def test_multiple_matches_all_returned_sorted() -> None:
    """Every match is returned in PID order. No silent first-pick."""
    matched = resolve_process_target(_target(executable="python"), OBSERVATIONS)

    assert len(matched) == 3
    assert [obs.pid for obs in matched] == sorted(obs.pid for obs in matched)


def test_matching_is_case_sensitive() -> None:
    """Case behavior is exact match, documented for operators."""
    matched = resolve_process_target(_target(executable="Python"), OBSERVATIONS)

    assert matched == []


def test_command_match_needs_visible_cmdline() -> None:
    """Processes without a command line never match a substring."""
    matched = resolve_process_target(
        _target(executable="python", command_contains="python"), OBSERVATIONS
    )

    assert [obs.pid for obs in matched] == [100, 300]
