"""Tests for the read-only ARC API endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient

from arc.api.app import create_app
from tests.conftest import write_contract


def _client(contracts_dir: Path | None = None) -> TestClient:
    if contracts_dir is None:
        return TestClient(create_app())
    return TestClient(create_app(contracts_dir=contracts_dir))


def test_system_endpoint_shape_and_ranges(tmp_path: Path) -> None:
    """System telemetry has the documented shape and sane ranges."""
    with _client(tmp_path) as client:
        response = client.get("/api/system")

    assert response.status_code == 200
    payload = response.json()
    assert 0.0 <= payload["cpu_percent"] <= 100.0
    assert 0.0 <= payload["memory_percent"] <= 100.0
    assert payload["cpu_count"] >= 1
    assert payload["timestamp"] > 0


def test_contracts_endpoint_lists_loaded_contract(tmp_path: Path) -> None:
    """Loaded contracts appear with preview evaluation info."""
    write_contract(tmp_path, "relief.yaml")
    with _client(tmp_path) as client:
        response = client.get("/api/contracts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["load_errors"] == []
    status = payload["contracts"][0]
    assert status["contract"]["id"] == "compile-relief"
    assert status["outcome"] in (
        "trigger_pending",
        "would_activate",
        "target_not_found",
        "disabled",
        "evaluation_error",
    )


def test_contracts_endpoint_reports_invalid_files(tmp_path: Path) -> None:
    """Invalid contract files surface as errors, not silent skips."""
    (tmp_path / "bad.yaml").write_text("version: [broken\n", encoding="utf-8")
    with _client(tmp_path) as client:
        response = client.get("/api/contracts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 0
    assert len(payload["load_errors"]) == 1
    assert payload["load_errors"][0]["file"] == "bad.yaml"


def test_processes_endpoint_default_limit(tmp_path: Path) -> None:
    """Process snapshots are bounded and ordered by PID."""
    with _client(tmp_path) as client:
        response = client.get("/api/processes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 100
    assert payload["count"] <= 100
    assert payload["total_observed"] >= payload["count"]
    pids = [proc["pid"] for proc in payload["processes"]]
    assert pids == sorted(pids)


def test_processes_endpoint_honors_small_limit(tmp_path: Path) -> None:
    """A small limit truncates the snapshot."""
    with _client(tmp_path) as client:
        response = client.get("/api/processes?limit=3")

    assert response.status_code == 200
    assert response.json()["count"] <= 3


def test_processes_endpoint_rejects_bad_limits(tmp_path: Path) -> None:
    """Zero, negative, and huge limits are rejected with 422."""
    with _client(tmp_path) as client:
        for bad in ("0", "-5", "5000"):
            response = client.get(f"/api/processes?limit={bad}")

            assert response.status_code == 422
