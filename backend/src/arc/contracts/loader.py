"""YAML loading and validation for ARC contracts.

Only direct ``.yaml``/``.yml`` files in the configured directory are
loaded, in sorted filename order. ``contracts/examples/`` is never loaded
implicitly, examples are documentation, not live policy.
"""

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from arc.contracts.models import Contract

logger = logging.getLogger(__name__)

CONTRACT_FILE_PATTERNS = ("*.yaml", "*.yml")


class ContractLoadError(Exception):
    """A contract file could not be loaded or validated."""

    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


def load_contract_file(path: Path) -> Contract:
    """Load and validate a single contract YAML file."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractLoadError(path, f"cannot read file: {exc.strerror or exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ContractLoadError(path, f"malformed YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractLoadError(path, "contract YAML must be a mapping at the top level")
    try:
        return Contract.model_validate(data)
    except ValidationError as exc:
        raise ContractLoadError(path, f"invalid contract: {exc}") from exc


def collect_contract_files(directory: Path) -> list[Path]:
    """Return direct ``.yaml``/``.yml`` files in ``directory``, sorted."""
    directory = Path(directory)
    files: list[Path] = []
    for pattern in CONTRACT_FILE_PATTERNS:
        files.extend(sorted(directory.glob(pattern)))
    return sorted(path for path in files if path.is_file())


def load_contract_directory(directory: Path) -> list[Contract]:
    """Load every contract file directly inside ``directory``.

    Files are processed in sorted name order for determinism. Invalid
    files raise ``ContractLoadError`` and are never silently ignored.
    Duplicate contract IDs raise ``ContractLoadError`` identifying both
    files.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise ContractLoadError(directory, "contracts directory does not exist")
    files = collect_contract_files(directory)

    contracts: list[Contract] = []
    seen: dict[str, Path] = {}
    for path in files:
        if not path.is_file():
            continue
        contract = load_contract_file(path)
        if contract.id in seen:
            raise ContractLoadError(
                path,
                f"duplicate contract id {contract.id!r} (also defined in {seen[contract.id]})",
            )
        seen[contract.id] = path
        contracts.append(contract)
        logger.info("contract loaded: %s (%s)", contract.id, path.name)
    return contracts
