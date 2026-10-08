"""Tests for WebSocket endpoint state streaming."""

from pathlib import Path

from fastapi.testclient import TestClient

from arc.api.app import create_app, websocket_state_payload
from arc.core.engine import ObservationEngine
from tests.conftest import make_fake


def test_websocket_initial_state(tmp_path: Path) -> None:
    fake = make_fake(pid=50)
    app = create_app(contracts_dir=tmp_path, auto_start=False, resource_adapter=fake)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "init"
            assert "status" in data
            assert "recent_events" in data
            assert data["status"]["running"] is True


def test_websocket_tick_payload_has_complete_event_and_telemetry_shape() -> None:
    engine = ObservationEngine(resource_adapter=make_fake(pid=50))
    engine.start()

    payload = websocket_state_payload(engine, "tick")

    assert payload["type"] == "tick"
    assert payload["telemetry"] is None
    assert set(payload["status"]) == {
        "running",
        "contract_count",
        "active_contracts",
        "error_contracts",
        "enforcement_supported",
        "cgroup_available",
        "cgroup_reason",
    }
    event = payload["recent_events"][0]
    assert set(event) == {
        "seq",
        "timestamp",
        "type",
        "severity",
        "contract_id",
        "pid",
        "message",
        "details",
    }
