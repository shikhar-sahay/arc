"""Tests for contract persistence, CRUD safety, and traversal protection."""

from pathlib import Path

import pytest

from arc.contracts.repository import (
    ContractPersistenceError,
    contract_path_for_id,
    delete_contract_file,
    find_contract_file,
    save_contract_file,
    validate_contract_id,
)
from tests.conftest import make_contract


def test_validate_contract_id_valid() -> None:
    validate_contract_id("compile-relief")
    validate_contract_id("web-worker-limit-1")
    validate_contract_id("a")


def test_validate_contract_id_invalid() -> None:
    with pytest.raises(ContractPersistenceError):
        validate_contract_id("../escape")
    with pytest.raises(ContractPersistenceError):
        validate_contract_id("HasUpperCase")
    with pytest.raises(ContractPersistenceError):
        validate_contract_id("spaces in name")
    with pytest.raises(ContractPersistenceError):
        validate_contract_id("")


def test_contract_path_for_id(tmp_path: Path) -> None:
    path = contract_path_for_id(tmp_path, "compile-relief")
    assert path == (tmp_path / "compile-relief.yaml").resolve()


def test_save_and_find_and_delete(tmp_path: Path) -> None:
    contract = make_contract(id="test-save-1")
    saved_path = save_contract_file(tmp_path, contract)

    assert saved_path.is_file()
    assert find_contract_file(tmp_path, "test-save-1") == saved_path

    # Delete
    deleted_path = delete_contract_file(tmp_path, "test-save-1")
    assert deleted_path == saved_path
    assert not saved_path.exists()
    assert find_contract_file(tmp_path, "test-save-1") is None


def test_save_atomic_update(tmp_path: Path) -> None:
    contract = make_contract(id="test-save-2", name="Initial")
    save_contract_file(tmp_path, contract)

    updated = contract.model_copy(update={"name": "Updated Name"})
    saved_path = save_contract_file(tmp_path, updated)

    assert saved_path.is_file()
    assert "Updated Name" in saved_path.read_text(encoding="utf-8")


def test_delete_nonexistent_raises(tmp_path: Path) -> None:
    with pytest.raises(ContractPersistenceError):
        delete_contract_file(tmp_path, "non-existent")
