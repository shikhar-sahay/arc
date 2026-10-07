"""Safe filesystem operations for contract YAML definitions.

Enforces:
1. Valid contract ID naming (no directory traversal).
2. Atomic file writes (temporary file in same directory, then rename).
3. Safe deletion.
4. Protection against duplicate IDs across files.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import yaml

from arc.contracts.loader import collect_contract_files, load_contract_file
from arc.contracts.models import CONTRACT_ID_PATTERN, Contract

_ID_RE = re.compile(CONTRACT_ID_PATTERN)


class ContractPersistenceError(Exception):
    """Failure during contract file operations."""


def validate_contract_id(contract_id: str) -> None:
    """Validate that contract_id is safe for use as a file base name."""
    if not isinstance(contract_id, str) or not _ID_RE.match(contract_id):
        raise ContractPersistenceError(
            f"invalid contract id {contract_id!r}: must match {CONTRACT_ID_PATTERN}"
        )


def contract_path_for_id(directory: Path, contract_id: str) -> Path:
    """Resolve the canonical YAML path for a given contract id."""
    validate_contract_id(contract_id)
    canonical_dir = directory.resolve()
    target_path = (canonical_dir / f"{contract_id}.yaml").resolve()
    # Guard against any path traversal escapes
    if target_path.parent != canonical_dir:
        raise ContractPersistenceError(f"path traversal detected for contract id: {contract_id}")
    return target_path


def find_contract_file(directory: Path, contract_id: str) -> Path | None:
    """Locate the existing YAML/YML file for a contract id if it exists."""
    validate_contract_id(contract_id)
    directory = directory.resolve()
    for ext in (".yaml", ".yml"):
        candidate = directory / f"{contract_id}{ext}"
        if candidate.is_file():
            return candidate
    # Also check if any existing file has this ID internally
    for file_path in collect_contract_files(directory):
        try:
            loaded = load_contract_file(file_path)
            if loaded.id == contract_id:
                return file_path
        except Exception:
            continue
    return None


def save_contract_file(directory: Path, contract: Contract) -> Path:
    """Atomically write a validated contract to a YAML file in directory.

    If the contract already exists under another filename, raises ContractPersistenceError
    to prevent duplicate definitions.
    """
    directory = directory.resolve()
    if not directory.is_dir():
        directory.mkdir(parents=True, exist_ok=True)

    validate_contract_id(contract.id)

    # Check for duplicate ID under a different file name
    existing_file = find_contract_file(directory, contract.id)
    target_file = contract_path_for_id(directory, contract.id)

    if existing_file is not None and existing_file.resolve() != target_file.resolve():
        target_file = existing_file  # Overwrite existing filename if updating

    content = yaml.safe_dump(contract.model_dump(mode="json"), sort_keys=False)

    # Atomic write via temp file in the same directory (ensures same filesystem for atomic rename)
    try:
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{contract.id}_", suffix=".tmp", dir=str(directory)
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(temp_path, target_file)
    except OSError as exc:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise ContractPersistenceError(f"failed to save contract {contract.id}: {exc}") from exc

    return target_file


def delete_contract_file(directory: Path, contract_id: str) -> Path:
    """Delete the YAML file for a given contract id."""
    existing_file = find_contract_file(directory, contract_id)
    if existing_file is None:
        raise ContractPersistenceError(f"contract {contract_id} file not found in {directory}")
    try:
        existing_file.unlink()
        return existing_file
    except OSError as exc:
        raise ContractPersistenceError(f"failed to delete contract {contract_id}: {exc}") from exc
