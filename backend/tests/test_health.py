"""Tests for the ARC health endpoint."""

import sys

from fastapi.testclient import TestClient

from arc.api.app import APP_NAME, create_app


def test_health_returns_ok_with_platform() -> None:
    """GET /api/health returns app name, ok status, and current platform."""
    client = TestClient(create_app())
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == APP_NAME
    assert payload["status"] == "ok"
    assert payload["platform"] == sys.platform


def test_health_content_type_is_json() -> None:
    """Health endpoint responds with JSON."""
    client = TestClient(create_app())
    response = client.get("/api/health")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
