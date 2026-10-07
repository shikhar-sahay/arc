"""ARC FastAPI application.

FastAPI is an interface to the ARC engine, not the engine itself. Every
endpoint here only reads engine state. Enforcement runs in the engine's
own loop (started in lifespan), never inside a GET handler.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from arc.api.schemas import (
    ContractListResponse,
    ContractLoadIssue,
    ContractStatus,
    EngineStatusResponse,
    EventListResponse,
    EventResponse,
    HealthResponse,
    ProcessListResponse,
    ProcessResponse,
    SystemResponse,
    TargetIdentityResponse,
)
from arc.contracts.loader import (
    ContractLoadError,
    collect_contract_files,
    load_contract_file,
    resolve_contracts_dir,
)
from arc.contracts.models import Contract
from arc.core.engine import ObservationEngine
from arc.linux.resources import ResourceAdapter
from arc.monitoring.processes import sample_processes
from arc.monitoring.system import SystemMonitor

logger = logging.getLogger(__name__)

APP_NAME = "ARC"
DEFAULT_PROCESS_LIMIT = 100
MAX_PROCESS_LIMIT = 1000
DEFAULT_EVENT_LIMIT = 100
MAX_EVENT_LIMIT = 500


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


def create_app(
    contracts_dir: Path | str | None = None,
    auto_start: bool = True,
    resource_adapter: ResourceAdapter | None = None,
    poll_interval_seconds: float = 5.0,
) -> FastAPI:
    """Create the ARC application around one persistent engine instance."""
    directory = resolve_contracts_dir(contracts_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        monitor = SystemMonitor()
        contracts, issues = load_contracts_lenient(directory)
        engine = ObservationEngine(
            contracts,
            poll_interval_seconds=poll_interval_seconds,
            system_monitor=monitor,
            resource_adapter=resource_adapter,
        )
        engine.start()
        app.state.monitor = monitor
        app.state.engine = engine
        app.state.contract_load_issues = issues
        task: asyncio.Task[None] | None = None
        if auto_start:
            task = asyncio.create_task(engine.run_forever())
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            problems = engine.shutdown()
            for problem in problems:
                logger.error("shutdown restoration problem: %s", problem)

    app = FastAPI(
        title="ARC",
        description="Adaptive Resource Contract Engine API (reads engine state only)",
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
        """Liveness plus engine summary. Never enforces."""
        status = app.state.engine.engine_status()
        return HealthResponse(
            app=APP_NAME,
            status="ok",
            platform=sys.platform,
            engine_running=status.running,
            enforcement_supported=status.enforcement_supported,
            contract_count=status.contract_count,
            active_contracts=status.active_contracts,
            error_contracts=status.error_contracts,
        )

    @app.get("/api/status", response_model=EngineStatusResponse)
    def get_status() -> EngineStatusResponse:
        """Full engine and capability report. Never enforces."""
        status = app.state.engine.engine_status()
        return EngineStatusResponse(
            running=status.running,
            platform=status.platform,
            enforcement_supported=status.enforcement_supported,
            euid=status.euid,
            privileged_hint=status.privileged_hint,
            poll_interval_seconds=status.poll_interval_seconds,
            contract_count=status.contract_count,
            active_contracts=status.active_contracts,
            error_contracts=status.error_contracts,
            event_count=status.event_count,
        )

    @app.get("/api/system", response_model=SystemResponse)
    def get_system() -> SystemResponse:
        """Latest engine telemetry. Never enforces."""
        snapshot = app.state.engine.latest_telemetry()
        if snapshot is None:
            try:
                snapshot = app.state.monitor.sample()
            except Exception as exc:
                logger.exception("system sampling failed")
                raise HTTPException(
                    status_code=500, detail=f"system sampling failed: {exc}"
                ) from exc
        return SystemResponse.from_snapshot(snapshot)

    @app.get("/api/contracts", response_model=ContractListResponse)
    def get_contracts() -> ContractListResponse:
        """Contract runtime state from the engine. Never enforces."""
        engine: ObservationEngine = app.state.engine
        statuses = [
            ContractStatus(
                contract=view.contract,
                lifecycle=view.lifecycle,
                outcome=view.outcome,
                matched_pids=view.matched_pids,
                active_targets=[
                    TargetIdentityResponse(
                        pid=identity.pid,
                        create_time=identity.create_time,
                        name=identity.name,
                    )
                    for identity in view.active_identities
                ],
                trigger_raw=view.trigger_raw,
                trigger_satisfied=view.trigger_satisfied,
                restore_raw=view.restore_raw,
                restore_satisfied=view.restore_satisfied,
                activated_at=view.activated_at,
                last_error=view.last_error,
            )
            for view in engine.contract_statuses()
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
        """Latest engine process snapshot, bounded. Never enforces."""
        observations = app.state.engine.latest_observations()
        if not observations:
            try:
                observations = sample_processes()
            except Exception as exc:
                logger.exception("process sampling failed")
                raise HTTPException(
                    status_code=500, detail=f"process sampling failed: {exc}"
                ) from exc
        page = observations[:limit]
        return ProcessListResponse(
            processes=[ProcessResponse.from_observation(obs) for obs in page],
            count=len(page),
            limit=limit,
            total_observed=len(observations),
        )

    @app.get("/api/events", response_model=EventListResponse)
    def get_events(
        limit: int = Query(default=DEFAULT_EVENT_LIMIT, ge=1, le=MAX_EVENT_LIMIT),
    ) -> EventListResponse:
        """Newest-first engine event history, bounded. Never enforces."""
        engine: ObservationEngine = app.state.engine
        events = engine.recent_events(limit)
        return EventListResponse(
            events=[EventResponse.from_event(event) for event in events],
            count=len(events),
            limit=limit,
        )

    return app


app = create_app()
