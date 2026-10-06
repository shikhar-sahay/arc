"""Shared helpers for ARC backend tests."""

from pathlib import Path
from typing import Any

import yaml

from arc.contracts.models import Contract


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
