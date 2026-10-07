"""ARC command line interface.

``arc validate`` only checks contracts (read-only). ``arc run`` starts
the real runtime engine headlessly: on Linux it enforces contracts, on
other platforms it observes and previews without touching resources.
Core runs without FastAPI or React either way.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from arc.contracts.loader import (
    ContractLoadError,
    collect_contract_files,
    load_contract_directory,
    load_contract_file,
    resolve_contracts_dir,
)
from arc.contracts.models import Contract
from arc.core.engine import ObservationEngine
from arc.linux.psutil_adapter import LinuxResourceAdapter


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
        description="Adaptive Resource Contract Engine",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser(
        "validate",
        help="validate a contract file or directory against the ARC schema",
    )
    validate.add_argument("path", help="contract YAML file or directory")

    run_parser = sub.add_parser(
        "run",
        help="run the ARC runtime engine headlessly until interrupted",
    )
    run_parser.add_argument(
        "--contracts",
        default=None,
        help="contracts directory (default: repository contracts/ or ARC_CONTRACTS_DIR)",
    )
    run_parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="polling interval in seconds (default: 5.0)",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns the process exit code (0 is success)."""
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return validate_path(args.path)
    if args.command == "run":
        return run_engine(args.contracts, args.interval)
    return 2


async def _print_new_events(engine: ObservationEngine, last_seq: int) -> int:
    """Print unseen events oldest-first. Returns the newest seq printed."""
    pending = [event for event in engine.recent_events(500) if event.seq > last_seq]
    for event in sorted(pending, key=lambda item: item.seq):
        print(f"[{event.type.value}] {event.message}", flush=True)
    if pending:
        return max(event.seq for event in pending)
    return last_seq


async def _serve(engine: ObservationEngine) -> None:
    """Run the engine loop while tailing its event history to stdout."""
    worker = asyncio.create_task(engine.run_forever())
    last_seq = 0
    try:
        while True:
            await asyncio.sleep(0.5)
            last_seq = await _print_new_events(engine, last_seq)
    except asyncio.CancelledError:
        pass
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        await _print_new_events(engine, last_seq)


def run_engine(contracts_raw: str | None, interval: float) -> int:
    """Load contracts and run the engine until Ctrl+C. Returns exit code."""
    if interval <= 0:
        print("error: --interval must be positive", file=sys.stderr)
        return 2
    directory = resolve_contracts_dir(contracts_raw)
    try:
        contracts = load_contract_directory(directory)
    except ContractLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not contracts:
        print(f"error: {directory}: no contract files found", file=sys.stderr)
        return 2
    engine = ObservationEngine(
        contracts,
        poll_interval_seconds=interval,
        resource_adapter=LinuxResourceAdapter(),
    )
    capabilities = engine.capabilities
    print(f"ARC engine starting on {capabilities.platform}", flush=True)
    print(
        f"enforcement_supported={capabilities.enforcement_supported} ({capabilities.reason})",
        flush=True,
    )
    if capabilities.euid is not None:
        print(f"euid={capabilities.euid} (hint only, not a verdict)", flush=True)
    for contract in contracts:
        print(f"loaded: {contract.id} ({contract.name})", flush=True)
    print("press Ctrl+C to stop (ACTIVE contracts restore on exit)", flush=True)
    engine.start()
    try:
        asyncio.run(_serve(engine))
    except KeyboardInterrupt:
        print("interrupted, restoring ARC-managed resources...", flush=True)
    problems = engine.shutdown()
    for problem in problems:
        print(f"error: shutdown restoration problem: {problem}", file=sys.stderr)
    print("ARC engine stopped", flush=True)
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> None:
    """Console entry point. Exits with the command result code."""
    sys.exit(run(argv))


if __name__ == "__main__":
    main()
