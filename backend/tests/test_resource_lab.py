"""Resource Lab API and controlled-process lifecycle tests."""

import sys
from pathlib import Path

import psutil
from fastapi.testclient import TestClient

from arc.api.app import create_app


def test_resource_lab_reports_platform_and_stopped_state(tmp_path: Path) -> None:
    with TestClient(create_app(contracts_dir=tmp_path, auto_start=False)) as client:
        response = client.get("/api/resource-lab")

    assert response.status_code == 200
    assert response.json()["state"] == "stopped"
    assert response.json()["supported"] is (sys.platform == "linux")


def test_resource_lab_scenario_owns_and_cleans_up_workers(tmp_path: Path) -> None:
    with TestClient(create_app(contracts_dir=tmp_path, auto_start=False)) as client:
        started = client.post("/api/resource-lab/start", json={"workers": 2})
        if sys.platform != "linux":
            assert started.status_code == 409
            return

        assert started.status_code == 200
        payload = started.json()
        assert payload["state"] == "baseline"
        assert payload["worker_count"] == 2
        assert payload["contract"]["contract"]["id"] == "resource-lab-cpu-contention"
        pids = [item["pid"] for item in payload["workloads"]]
        assert len(pids) == 4
        assert all("arc-resource-lab" in " ".join(psutil.Process(pid).cmdline()) for pid in pids)
        assert [item["role"] for item in payload["workloads"]].count("suspension-target") == 1

        assert client.post("/api/resource-lab/start", json={"workers": 1}).status_code == 409
        assert client.post("/api/resource-lab/pressure", json={"high": True}).status_code == 200
        assert client.post("/api/resource-lab/pressure", json={"high": False}).status_code == 200
        stopped = client.post("/api/resource-lab/stop")
        assert stopped.status_code == 200
        assert stopped.json()["state"] == "stopped"
        assert all(not psutil.pid_exists(pid) for pid in pids)
