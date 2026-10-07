"""Tests for contract CRUD and reload API endpoints."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arc.api.app import create_app
from arc.linux.fake_adapter import FakeResourceAdapter
from tests.conftest import make_fake, valid_contract_data


@pytest.fixture
def api_client(tmp_path: Path) -> tuple[TestClient, Path, FakeResourceAdapter]:
    fake = make_fake(pid=50)
    app = create_app(contracts_dir=tmp_path, auto_start=False, resource_adapter=fake)
    with TestClient(app) as client:
        yield client, tmp_path, fake


def test_contract_crud_workflow(api_client) -> None:
    client, contracts_dir, fake = api_client

    # 1. Initially empty
    resp = client.get("/api/contracts")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0

    # 2. Validate valid payload
    data = valid_contract_data(id="crud-contract")
    val_resp = client.post("/api/contracts/validate", json=data)
    assert val_resp.status_code == 200
    assert val_resp.json()["valid"] is True

    # 3. Create contract
    create_resp = client.post("/api/contracts", json=data)
    assert create_resp.status_code == 200
    assert create_resp.json()["contract"]["id"] == "crud-contract"

    # Verify persisted to disk
    assert (contracts_dir / "crud-contract.yaml").is_file()

    # 4. Duplicate create returns 409
    dup_resp = client.post("/api/contracts", json=data)
    assert dup_resp.status_code == 409

    # 5. Toggle enabled
    toggle_resp = client.patch("/api/contracts/crud-contract/enabled", json={"enabled": False})
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["contract"]["enabled"] is False

    # 6. Update contract
    data["name"] = "Updated CRUD Contract"
    data["enabled"] = False
    put_resp = client.put("/api/contracts/crud-contract", json=data)
    assert put_resp.status_code == 200
    assert put_resp.json()["contract"]["name"] == "Updated CRUD Contract"

    # 7. Reload engine from disk
    reload_resp = client.post("/api/engine/reload")
    assert reload_resp.status_code == 200
    assert reload_resp.json()["contract_count"] == 1

    # 8. Delete contract
    del_resp = client.delete("/api/contracts/crud-contract")
    assert del_resp.status_code == 200
    assert not (contracts_dir / "crud-contract.yaml").exists()

    resp_after = client.get("/api/contracts")
    assert resp_after.json()["count"] == 0


def test_enriched_processes_endpoint(api_client) -> None:
    client, contracts_dir, fake = api_client
    resp = client.get("/api/processes")
    assert resp.status_code == 200
    data = resp.json()
    assert "processes" in data
    assert "total_observed" in data
