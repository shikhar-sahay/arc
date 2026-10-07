"""Tests for ARC API endpoints reading engine state (never enforcing)."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arc.api.app import create_app
from arc.core.lifecycle import LifecycleState
from tests.conftest import make_observation, make_telemetry, write_contract


def _client(
    contracts_dir: Path | None = None,
    adapter=None,
    auto_start: bool = False,
) -> TestClient:
    return TestClient(
        create_app(contracts_dir=contracts_dir, auto_start=auto_start, resource_adapter=adapter)
    )


def _drive(client: TestClient, cpu: float, now: float) -> None:
    engine = client.app.state.engine
    engine.step(make_telemetry(cpu=cpu), [make_observation()], now=now)


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


def test_system_endpoint_serves_engine_cache(tmp_path: Path) -> None:
    """After a step, system reflects the engine snapshot, not a new sample."""
    from tests.conftest import make_fake

    with _client(tmp_path, adapter=make_fake()) as client:
        client.app.state.engine.step(make_telemetry(cpu=33.0), [], now=0.0)
        payload = client.get("/api/system").json()

    assert payload["cpu_percent"] == 33.0


def test_contracts_endpoint_reflects_engine_lifecycle(tmp_path: Path) -> None:
    """Contracts show lifecycle, identities, and restore status from steps."""
    from tests.conftest import make_fake

    write_contract(tmp_path, "relief.yaml")
    with _client(tmp_path, adapter=make_fake()) as client:
        _drive(client, cpu=80.0, now=0.0)
        _drive(client, cpu=80.0, now=5.0)
        response = client.get("/api/contracts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["load_errors"] == []
    status = payload["contracts"][0]
    assert status["contract"]["id"] == "compile-relief"
    assert status["lifecycle"] == "active"
    assert status["outcome"] == "activated"
    assert status["matched_pids"] == [50]
    assert status["active_targets"][0]["pid"] == 50
    assert status["active_targets"][0]["create_time"] == 1000.0
    assert status["activated_at"] is not None


def test_get_requests_do_not_enforce(tmp_path: Path) -> None:
    """Repeated GETs cause zero adapter calls and no lifecycle movement."""
    from tests.conftest import make_fake

    fake = make_fake()
    write_contract(tmp_path, "relief.yaml")
    with _client(tmp_path, adapter=fake) as client:
        _drive(client, cpu=80.0, now=0.0)
        calls_after_step = len(fake.calls)
        for _ in range(3):
            assert client.get("/api/contracts").status_code == 200
            assert client.get("/api/system").status_code == 200
            assert client.get("/api/processes").status_code == 200
            assert client.get("/api/events").status_code == 200

    assert len(fake.calls) == calls_after_step
    assert client.app.state.engine.runtime_for("compile-relief").lifecycle is (
        LifecycleState.INACTIVE
    )


def test_status_endpoint_reports_capabilities(tmp_path: Path) -> None:
    """Status distinguishes liveness, support, privilege hint, counts."""
    with _client(tmp_path) as client:
        payload = client.get("/api/status").json()

    assert payload["running"] is True
    assert payload["platform"] == sys.platform
    assert payload["enforcement_supported"] is (sys.platform == "linux")
    assert payload["contract_count"] == 0
    assert payload["poll_interval_seconds"] > 0


def test_events_endpoint_lists_newest_first(tmp_path: Path) -> None:
    """Events come back newest first with a validated bound."""
    from tests.conftest import make_fake

    write_contract(tmp_path, "relief.yaml")
    with _client(tmp_path, adapter=make_fake()) as client:
        _drive(client, cpu=80.0, now=0.0)
        _drive(client, cpu=80.0, now=5.0)
        payload = client.get("/api/events?limit=100").json()

    assert payload["limit"] == 100
    assert payload["count"] > 0
    seqs = [event["seq"] for event in payload["events"]]
    assert seqs == sorted(seqs, reverse=True)
    assert any(event["type"] == "contract_activated" for event in payload["events"])


def test_events_endpoint_rejects_bad_limits(tmp_path: Path) -> None:
    """Zero, negative, and huge event limits are rejected with 422."""
    with _client(tmp_path) as client:
        for bad in ("0", "-5", "501"):
            assert client.get(f"/api/events?limit={bad}").status_code == 422


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


def test_processes_endpoint_rejects_bad_limits(tmp_path: Path) -> None:
    """Zero, negative, and huge limits are rejected with 422."""
    with _client(tmp_path) as client:
        for bad in ("0", "-5", "5000"):
            response = client.get(f"/api/processes?limit={bad}")

            assert response.status_code == 422


@pytest.mark.skipif(sys.platform == "linux", reason="Windows-only fallback check")
def test_windows_reports_no_enforcement_support(tmp_path: Path) -> None:
    """On Windows the API honestly reports enforcement as unsupported."""
    with _client(tmp_path) as client:
        status = client.get("/api/status").json()

    assert status["enforcement_supported"] is False
