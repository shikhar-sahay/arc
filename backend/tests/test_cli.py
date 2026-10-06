"""Tests for the ARC contract validation CLI."""

from pathlib import Path

import pytest

from arc.cli.main import run
from tests.conftest import write_contract


def test_validate_valid_file_succeeds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A valid contract exits 0 and names the contract."""
    path = write_contract(tmp_path, "good.yaml")

    assert run(["validate", str(path)]) == 0
    assert "compile-relief" in capsys.readouterr().out


def test_validate_invalid_file_fails(tmp_path: Path) -> None:
    """A schema violation exits non-zero."""
    path = tmp_path / "bad.yaml"
    path.write_text("version: [broken\n", encoding="utf-8")

    assert run(["validate", str(path)]) == 1


def test_validate_missing_file_fails(tmp_path: Path) -> None:
    """A missing path exits non-zero."""
    assert run(["validate", str(tmp_path / "absent.yaml")]) == 1


def test_validate_directory_checks_every_file(tmp_path: Path) -> None:
    """A directory of valid contracts exits 0."""
    write_contract(tmp_path, "a.yaml", id="a-id", name="A")
    write_contract(
        tmp_path,
        "b.yaml",
        id="b-id",
        name="B",
        target={
            "type": "process",
            "match": {"executable": "other"},
        },
    )

    assert run(["validate", str(tmp_path)]) == 0


def test_validate_directory_with_duplicates_fails(tmp_path: Path) -> None:
    """Duplicate IDs in one directory exit non-zero."""
    write_contract(tmp_path, "a.yaml", id="dup-id", name="A")
    write_contract(tmp_path, "b.yaml", id="dup-id", name="B")

    assert run(["validate", str(tmp_path)]) == 1
