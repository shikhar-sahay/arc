"""ARC command line interface (read-only helpers).

Only validation and inspection live here. Nothing in the CLI changes
process or resource state.
"""

import argparse
import sys
from pathlib import Path

from arc.contracts.loader import (
    ContractLoadError,
    collect_contract_files,
    load_contract_directory,
    load_contract_file,
)
from arc.contracts.models import Contract


def _report_contract(contract: Contract) -> None:
    print(f"ok: {contract.id} ({contract.name})")


def validate_file(path: Path) -> int:
    """Validate one contract file. Return 0 on success, 1 on failure."""
    try:
        contract = load_contract_file(path)
    except ContractLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _report_contract(contract)
    return 0


def validate_directory(directory: Path) -> int:
    """Validate every contract file directly in a directory."""
    if not directory.is_dir():
        print(f"error: {directory}: not a directory", file=sys.stderr)
        return 1
    files = collect_contract_files(directory)
    if not files:
        print(f"error: {directory}: no contract files found", file=sys.stderr)
        return 1
    try:
        contracts = load_contract_directory(directory)
    except ContractLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for contract in contracts:
        _report_contract(contract)
    return 0


def validate_path(raw_path: str) -> int:
    """Validate a contract file or a directory of contract files."""
    path = Path(raw_path)
    if path.is_dir():
        return validate_directory(path)
    return validate_file(path)


def build_parser() -> argparse.ArgumentParser:
    """Build the ARC argument parser."""
    parser = argparse.ArgumentParser(
        prog="arc",
        description="Adaptive Resource Contract Engine helpers (read-only)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser(
        "validate",
        help="validate a contract file or directory against the ARC schema",
    )
    validate.add_argument("path", help="contract YAML file or directory")
    return parser


def run(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns the process exit code (0 is success)."""
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return validate_path(args.path)
    return 2


def main(argv: list[str] | None = None) -> None:
    """Console entry point. Exits with the command result code."""
    sys.exit(run(argv))


if __name__ == "__main__":
    main()
