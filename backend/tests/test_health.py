"""Tests for the ARC health endpoint."""

import sys

from fastapi.testclient import TestClient

from arc.api.app import APP_NAME, create_app


def test_health_returns_ok_with_platform() -> None:
    """GET /api/health returns app name, ok status, and current platform."""
    with TestClient(create_app()) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == APP_NAME
    assert payload["status"] == "ok"
    assert payload["platform"] == sys.platform


def test_health_content_type_is_json() -> None:
    """Health endpoint responds with JSON."""
    with TestClient(create_app()) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]


def test_health_reports_engine_summary(tmp_path) -> None:
    """Health includes engine running state and contract counts."""
    with TestClient(create_app(contracts_dir=tmp_path)) as client:
        payload = client.get("/api/health").json()

    assert payload["engine_running"] is True
    assert payload["enforcement_supported"] is (sys.platform == "linux")
    assert payload["contract_count"] == 0
    assert payload["active_contracts"] == 0
    assert payload["error_contracts"] == 0
