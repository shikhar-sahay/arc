"""Tests for YAML contract loading and validation."""

from pathlib import Path

import pytest
import yaml

from arc.contracts.loader import (
    ContractLoadError,
    load_contract_directory,
    load_contract_file,
)
from tests.conftest import valid_contract_data, write_contract


def test_load_single_valid_file(tmp_path: Path) -> None:
    """A valid file loads into a validated contract."""
    path = write_contract(tmp_path, "relief.yaml")

    contract = load_contract_file(path)

    assert contract.id == "compile-relief"


def test_load_yml_extension(tmp_path: Path) -> None:
    """Both .yaml and .yml extensions are accepted."""
    path = write_contract(tmp_path, "relief.yml")

    assert load_contract_file(path).id == "compile-relief"


def test_malformed_yaml_reports_file(tmp_path: Path) -> None:
    """Broken YAML raises an error naming the file."""
    path = tmp_path / "broken.yaml"
    path.write_text("version: [unclosed\n  bad: : :\n", encoding="utf-8")

    with pytest.raises(ContractLoadError, match="broken.yaml"):
        load_contract_file(path)


def test_non_mapping_yaml_rejected(tmp_path: Path) -> None:
    """A top-level list is not a contract."""
    path = tmp_path / "list.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")

    with pytest.raises(ContractLoadError, match="must be a mapping"):
        load_contract_file(path)


def test_invalid_contract_is_not_silently_ignored(tmp_path: Path) -> None:
    """Schema violations raise instead of being skipped."""
    data = valid_contract_data()
    data["actions"] = []
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(ContractLoadError, match="bad.yaml"):
        load_contract_file(path)


def test_missing_file_reports_error(tmp_path: Path) -> None:
    """Unreadable files produce a clear error."""
    with pytest.raises(ContractLoadError, match="nope.yaml"):
        load_contract_file(tmp_path / "nope.yaml")


def test_duplicate_ids_rejected_with_both_files(tmp_path: Path) -> None:
    """Two files with the same ID fail and name the conflict."""
    write_contract(tmp_path, "a.yaml", id="same-id", name="First")
    write_contract(tmp_path, "b.yaml", id="same-id", name="Second")

    with pytest.raises(ContractLoadError, match="same-id"):
        load_contract_directory(tmp_path)


def test_directory_loading_is_deterministic(tmp_path: Path) -> None:
    """Contracts come back in sorted filename order."""
    write_contract(tmp_path, "b.yaml", id="b-id", name="B")
    write_contract(tmp_path, "a.yaml", id="a-id", name="A")

    contracts = load_contract_directory(tmp_path)

    assert [contract.id for contract in contracts] == ["a-id", "b-id"]


def test_examples_subdirectory_is_not_loaded(tmp_path: Path) -> None:
    """Only direct files are live. Nested examples stay documentation."""
    nested = tmp_path / "examples"
    nested.mkdir()
    (nested / "example.yaml").write_text(yaml.safe_dump(valid_contract_data()), encoding="utf-8")

    assert load_contract_directory(tmp_path) == []


def test_missing_directory_reports_error(tmp_path: Path) -> None:
    """A missing contracts directory fails with context."""
    with pytest.raises(ContractLoadError, match="does not exist"):
        load_contract_directory(tmp_path / "absent")
