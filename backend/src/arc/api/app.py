"""ARC FastAPI application.

FastAPI is an interface to the ARC engine, not the engine itself. All
endpoints in this pass are read-only: health, live system telemetry,
loaded contract definitions with preview evaluations, and a bounded
process snapshot. Nothing here changes process or resource state.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from arc.api.schemas import (
    ContractListResponse,
    ContractLoadIssue,
    ContractStatus,
    HealthResponse,
    ProcessListResponse,
    ProcessResponse,
    SystemResponse,
)
from arc.contracts.loader import (
    ContractLoadError,
    collect_contract_files,
    load_contract_file,
)
from arc.contracts.models import Contract
from arc.core.engine import ObservationEngine
from arc.monitoring.processes import sample_processes
from arc.monitoring.system import SystemMonitor

logger = logging.getLogger(__name__)

APP_NAME = "ARC"
DEFAULT_PROCESS_LIMIT = 100
MAX_PROCESS_LIMIT = 1000


def default_contracts_dir() -> Path:
    """Repository-level contracts directory (live contracts, not examples)."""
    return Path(__file__).resolve().parents[4] / "contracts"


def resolve_contracts_dir(explicit: Path | str | None = None) -> Path:
    """Explicit path, ARC_CONTRACTS_DIR, or the repository default."""
    if explicit is not None:
        return Path(explicit)
    configured = os.environ.get("ARC_CONTRACTS_DIR")
    if configured:
        return Path(configured)
    return default_contracts_dir()


def load_contracts_lenient(directory: Path) -> tuple[list[Contract], list[ContractLoadIssue]]:
    """Load contracts, collecting per-file errors instead of failing fast.

    Invalid files are reported, never silently ignored. Duplicate IDs are
    reported against both files and only the first occurrence is kept.
    """
    contracts: list[Contract] = []
    issues: list[ContractLoadIssue] = []
    seen: dict[str, str] = {}
    if not directory.is_dir():
        logger.warning("contracts directory does not exist: %s", directory)
        return contracts, issues
    for path in collect_contract_files(directory):
        try:
            contract = load_contract_file(path)
        except ContractLoadError as exc:
            logger.warning("invalid contract file: %s", exc)
            issues.append(ContractLoadIssue(file=path.name, error=exc.message))
            continue
        if contract.id in seen:
            message = f"duplicate contract id {contract.id!r} (also defined in {seen[contract.id]})"
            logger.warning("%s: %s", path.name, message)
            issues.append(ContractLoadIssue(file=path.name, error=message))
            continue
        seen[contract.id] = path.name
        contracts.append(contract)
        logger.info("contract loaded: %s (%s)", contract.id, path.name)
    return contracts, issues


def create_app(contracts_dir: Path | str | None = None) -> FastAPI:
    """Create and configure the ARC FastAPI application."""
    directory = resolve_contracts_dir(contracts_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        monitor = SystemMonitor()
        contracts, issues = load_contracts_lenient(directory)
        app.state.monitor = monitor
        app.state.engine = ObservationEngine(contracts)
        app.state.contract_load_issues = issues
        yield

    app = FastAPI(
        title="ARC",
        description="Adaptive Resource Contract Engine API (read-only)",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=HealthResponse)
    def get_health() -> HealthResponse:
        """Return service health and runtime platform info."""
        return HealthResponse(app=APP_NAME, status="ok", platform=sys.platform)

    @app.get("/api/system", response_model=SystemResponse)
    def get_system() -> SystemResponse:
        """Return one fresh, read-only system telemetry snapshot."""
        try:
            snapshot = app.state.monitor.sample()
        except Exception as exc:
            logger.exception("system sampling failed")
            raise HTTPException(status_code=500, detail=f"system sampling failed: {exc}") from exc
        return SystemResponse.from_snapshot(snapshot)

    @app.get("/api/contracts", response_model=ContractListResponse)
    def get_contracts() -> ContractListResponse:
        """Return loaded contracts with their latest preview evaluations."""
        engine: ObservationEngine = app.state.engine
        try:
            cycle = engine.poll()
        except Exception as exc:
            logger.exception("contract evaluation failed")
            raise HTTPException(
                status_code=500, detail=f"contract evaluation failed: {exc}"
            ) from exc
        by_id = {evaluation.contract_id: evaluation for evaluation in cycle.evaluations}
        statuses = [
            ContractStatus(
                contract=contract,
                outcome=by_id[contract.id].outcome,
                matched_pids=by_id[contract.id].matched_pids,
                trigger_raw=by_id[contract.id].trigger_raw,
                trigger_satisfied=by_id[contract.id].trigger_satisfied,
                detail=by_id[contract.id].detail,
                error=by_id[contract.id].error,
            )
            for contract in engine.contracts
        ]
        return ContractListResponse(
            contracts=statuses,
            count=len(statuses),
            load_errors=list(app.state.contract_load_issues),
        )

    @app.get("/api/processes", response_model=ProcessListResponse)
    def get_processes(
        limit: int = Query(default=DEFAULT_PROCESS_LIMIT, ge=1, le=MAX_PROCESS_LIMIT),
    ) -> ProcessListResponse:
        """Return a bounded, read-only process snapshot ordered by PID."""
        try:
            observations = sample_processes()
        except Exception as exc:
            logger.exception("process sampling failed")
            raise HTTPException(status_code=500, detail=f"process sampling failed: {exc}") from exc
        page = observations[:limit]
        return ProcessListResponse(
            processes=[ProcessResponse.from_observation(obs) for obs in page],
            count=len(page),
            limit=limit,
            total_observed=len(observations),
        )

    return app


app = create_app()
