"""Shared helpers for ARC backend tests."""

from pathlib import Path
from typing import Any

import yaml

from arc.contracts.models import Contract
from arc.core.engine import ObservationEngine
from arc.linux.fake_adapter import FakeProcess, FakeResourceAdapter
from arc.linux.resources import UnsupportedPlatformError
from arc.monitoring.processes import ProcessObservation
from arc.monitoring.system import SystemSnapshot


def valid_contract_data(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid contract mapping with optional overrides."""
    data: dict[str, Any] = {
        "version": 1,
        "id": "compile-relief",
        "name": "Compilation Relief",
        "description": "Reduce contention while compiling.",
        "enabled": True,
        "target": {
            "type": "process",
            "match": {"executable": "python", "command_contains": "demo_cpu_worker"},
        },
        "trigger": {
            "metric": "system.cpu.percent",
            "operator": "gt",
            "value": 75,
            "for_seconds": 5,
        },
        "actions": [{"type": "nice", "value": 10}],
        "restore": {
            "metric": "system.cpu.percent",
            "operator": "lt",
            "value": 55,
            "for_seconds": 5,
        },
    }
    data.update(overrides)
    return data


def make_contract(**overrides: Any) -> Contract:
    """Build a validated contract with optional field overrides."""
    return Contract.model_validate(valid_contract_data(**overrides))


def write_contract(tmp_path: Path, filename: str, **overrides: Any) -> Path:
    """Write a valid contract YAML file into a temporary directory."""
    path = tmp_path / filename
    path.write_text(yaml.safe_dump(valid_contract_data(**overrides)), encoding="utf-8")
    return path


def make_telemetry(cpu: float = 80.0, memory: float = 30.0) -> SystemSnapshot:
    """Build a telemetry snapshot with chosen utilization."""
    return SystemSnapshot(cpu_percent=cpu, memory_percent=memory, cpu_count=4, timestamp=0.0)


def make_observation(
    pid: int = 50,
    name: str | None = "python",
    cmdline: str | None = "python demo_cpu_worker.py",
) -> ProcessObservation:
    """Build one process observation matching the default contract target."""
    return ProcessObservation(
        pid=pid, name=name, cmdline=cmdline, cpu_percent=90.0, memory_percent=2.0
    )


def make_fake(
    pid: int = 50,
    nice: int = 0,
    affinity: tuple[int, ...] = (0, 1, 2, 3),
    create_time: float = 1000.0,
    name: str | None = "python",
) -> FakeResourceAdapter:
    """Build a fake adapter seeded with one live process."""
    adapter = FakeResourceAdapter()
    adapter.add_process(
        FakeProcess(pid=pid, create_time=create_time, name=name, nice=nice, affinity=affinity)
    )
    return adapter


def make_engine(
    contracts: list[Contract] | None = None,
    adapter: FakeResourceAdapter | None = None,
    interval: float = 5.0,
) -> tuple[ObservationEngine, FakeResourceAdapter]:
    """Build an engine wired to a fake adapter (deterministic everywhere)."""
    adapter = adapter if adapter is not None else make_fake()
    if contracts is None:
        contracts = [make_contract()]
    engine = ObservationEngine(contracts, poll_interval_seconds=interval, resource_adapter=adapter)
    return engine, adapter


class DenyingAdapter:
    """Adapter stub reporting no enforcement support (preview-only mode)."""

    @property
    def enforcement_supported(self) -> bool:
        return False

    def _refuse(self, operation: str, pid: int | None = None):
        raise UnsupportedPlatformError(operation, pid, "no enforcement support")

    def get_identity(self, pid: int):
        return self._refuse("get_identity", pid)

    def get_nice(self, pid: int):
        return self._refuse("get_nice", pid)

    def set_nice(self, pid: int, value: int):
        return self._refuse("set_nice", pid)

    def get_affinity(self, pid: int):
        return self._refuse("get_affinity", pid)

    def set_affinity(self, pid: int, cpus):
        return self._refuse("set_affinity", pid)
