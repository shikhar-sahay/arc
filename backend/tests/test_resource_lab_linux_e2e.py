"""Opt-in end-to-end Resource Lab validation against the real Linux kernel."""

import os
import sys
import time
from pathlib import Path

import psutil
import pytest
from fastapi.testclient import TestClient

from arc.api.app import create_app

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or os.environ.get("ARC_RUN_LINUX_E2E") != "1",
    reason="set ARC_RUN_LINUX_E2E=1 on Linux to run the measured scenario",
)


def _wait_for(client: TestClient, lifecycle: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        last = client.get("/api/resource-lab").json()
        if last.get("contract", {}).get("lifecycle") == lifecycle:
            return last
        time.sleep(0.5)
    pytest.fail(f"contract did not reach {lifecycle}: {last}")


def _average_rates(client: TestClient, seconds: float = 2.0) -> tuple[float, float]:
    foreground: list[float] = []
    background: list[float] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        sample = client.get("/api/resource-lab").json()
        foreground.append(sample["foreground_operations_per_second"])
        background.append(sample["background_operations_per_second"])
        time.sleep(0.25)
    return sum(foreground) / len(foreground), sum(background) / len(background)


def _wait_for_contract(
    client: TestClient, contract_id: str, lifecycle: str, timeout: float = 20.0
) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        contracts = client.get("/api/contracts").json()["contracts"]
        last = next(item for item in contracts if item["contract"]["id"] == contract_id)
        if last["lifecycle"] == lifecycle:
            return last
        time.sleep(0.5)
    pytest.fail(f"{contract_id} did not reach {lifecycle}: {last}")


def test_three_measured_pressure_enforcement_restoration_cycles(tmp_path: Path) -> None:
    """GUI API to engine to kernel and back, repeated three times."""
    with TestClient(
        create_app(contracts_dir=tmp_path, auto_start=True, poll_interval_seconds=0.5)
    ) as client:
        started = client.post("/api/resource-lab/start", json={"workers": 10})
        assert started.status_code == 200
        original = {
            item["pid"]: item["original_affinity"]
            for item in started.json()["workloads"]
            if item["role"] == "background"
        }
        assert client.post("/api/resource-lab/policy", json={"enabled": True}).status_code == 200

        baseline = _average_rates(client)
        contention: tuple[float, float] | None = None
        enforced: tuple[float, float] | None = None

        for cycle in range(3):
            assert client.post("/api/resource-lab/pressure", json={"high": True}).status_code == 200
            if cycle == 0:
                contention = _average_rates(client)
            active = _wait_for(client, "active")
            background = [item for item in active["workloads"] if item["role"] == "background"]
            assert active["background_operations_per_second"] > 0
            assert all(item["affinity"] == [active["policy_cpu"]] for item in background)
            if cycle == 0:
                enforced = _average_rates(client)

            assert (
                client.post("/api/resource-lab/pressure", json={"high": False}).status_code == 200
            )
            restored = _wait_for(client, "inactive")
            background = [item for item in restored["workloads"] if item["role"] == "background"]
            assert all(item["affinity"] == original[item["pid"]] for item in background)

        recovery = _average_rates(client)
        print(
            "Resource Lab rates (foreground, background ops/s): "
            f"baseline={baseline}, contention={contention}, "
            f"enforced={enforced}, recovery={recovery}"
        )

        assert client.post("/api/resource-lab/stop").status_code == 200


def test_separate_suspension_target_does_not_remove_pressure(tmp_path: Path) -> None:
    """Pressure workers keep running while ARC stops and restores a separate target."""
    contract_id = "resource-lab-suspension-e2e"
    contract = {
        "version": 1,
        "id": contract_id,
        "name": "Resource Lab Suspension E2E",
        "description": "Stop only the lab-owned idle verification target.",
        "enabled": True,
        "target": {
            "type": "process",
            "match": {
                "executable": "python",
                "command_contains": "arc-resource-lab-suspension-target",
            },
        },
        "trigger": {
            "metric": "system.cpu.percent",
            "operator": "gt",
            "value": 20,
            "for_seconds": 1,
        },
        "actions": [{"type": "suspend"}],
        "restore": {
            "metric": "system.cpu.percent",
            "operator": "lt",
            "value": 10,
            "for_seconds": 1,
        },
    }
    with TestClient(
        create_app(contracts_dir=tmp_path, auto_start=True, poll_interval_seconds=0.5)
    ) as client:
        started = client.post("/api/resource-lab/start", json={"workers": 10})
        assert started.status_code == 200
        target = next(
            item for item in started.json()["workloads"] if item["role"] == "suspension-target"
        )
        assert client.post("/api/contracts", json=contract).status_code == 200

        assert client.post("/api/resource-lab/pressure", json={"high": True}).status_code == 200
        _wait_for_contract(client, contract_id, "active")
        active = client.get("/api/resource-lab").json()
        assert active["background_operations_per_second"] > 0
        assert psutil.Process(target["pid"]).status() == psutil.STATUS_STOPPED
        assert client.post("/api/resource-lab/stop").status_code == 409

        assert client.post("/api/resource-lab/pressure", json={"high": False}).status_code == 200
        _wait_for_contract(client, contract_id, "inactive")
        assert psutil.Process(target["pid"]).status() != psutil.STATUS_STOPPED
        assert client.post("/api/resource-lab/stop").status_code == 200
