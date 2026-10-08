"""ARC FastAPI application.

FastAPI is an interface to the ARC engine, not the engine itself. Every
endpoint here only reads engine state. Enforcement runs in the engine's
own loop (started in lifespan), never inside a GET handler.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    Body,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi import (
    Path as PathParam,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
from arc.contracts.repository import (
    ContractPersistenceError,
    delete_contract_file,
    save_contract_file,
)
from arc.core.engine import ContractStatusView, ObservationEngine
from arc.core.lifecycle import LifecycleState
from arc.lab import ResourceLabController
from arc.lab.controller import ResourceLabError
from arc.linux.resources import ResourceAdapter
from arc.monitoring.processes import sample_processes
from arc.monitoring.system import SystemMonitor
from arc.observability.events import ArcEvent

logger = logging.getLogger(__name__)

APP_NAME = "ARC"
DEFAULT_PROCESS_LIMIT = 100
MAX_PROCESS_LIMIT = 1000
DEFAULT_EVENT_LIMIT = 100
MAX_EVENT_LIMIT = 500


class ToggleEnabledRequest(BaseModel):
    enabled: bool


class ResourceLabStartRequest(BaseModel):
    workers: int = 4


class ResourceLabPressureRequest(BaseModel):
    high: bool


LAB_CONTRACT_ID = "resource-lab-cpu-contention"


class ValidateContractResponse(BaseModel):
    valid: bool
    contract: Contract | None = None
    error: str | None = None


class ConnectionManager:
    """Manages active WebSocket connections for engine broadcast."""

    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        stale: list[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                stale.append(connection)
        for dead in stale:
            self.disconnect(dead)


def _contract_status_response(view: ContractStatusView) -> ContractStatus:
    """Use one response shape for contract list and mutation endpoints."""
    return ContractStatus(
        contract=view.contract,
        lifecycle=view.lifecycle,
        outcome=view.outcome,
        matched_pids=view.matched_pids,
        active_targets=[
            TargetIdentityResponse(
                pid=identity.pid,
                create_time=identity.create_time,
                name=identity.name,
                start_time_ticks=identity.start_time_ticks,
            )
            for identity in view.active_identities
        ],
        trigger_raw=view.trigger_raw,
        trigger_satisfied=view.trigger_satisfied,
        restore_raw=view.restore_raw,
        restore_satisfied=view.restore_satisfied,
        activated_at=view.activated_at,
        last_error=view.last_error,
        trigger_elapsed_seconds=view.trigger_elapsed_seconds,
        restore_elapsed_seconds=view.restore_elapsed_seconds,
    )


def _event_payload(event: ArcEvent) -> dict[str, object]:
    """Serialize the complete event shape used by REST and WebSocket clients."""
    return EventResponse.from_event(event).model_dump(mode="json")


def websocket_state_payload(engine: ObservationEngine, message_type: str) -> dict[str, object]:
    """Build a complete observation-only WebSocket state message."""
    status = engine.engine_status()
    telemetry = engine.latest_telemetry()
    return {
        "type": message_type,
        "status": {
            "running": status.running,
            "contract_count": status.contract_count,
            "active_contracts": status.active_contracts,
            "error_contracts": status.error_contracts,
            "enforcement_supported": status.enforcement_supported,
            "cgroup_available": status.cgroup_available,
            "cgroup_reason": status.cgroup_reason,
        },
        "telemetry": (
            {
                "cpu_percent": telemetry.cpu_percent,
                "memory_percent": telemetry.memory_percent,
                "cpu_count": telemetry.cpu_count,
                "timestamp": telemetry.timestamp,
                "cpu_per_core_percent": list(telemetry.cpu_per_core_percent),
            }
            if telemetry
            else None
        ),
        "recent_events": [_event_payload(ev) for ev in engine.recent_events(5)],
    }


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
    ws_manager = ConnectionManager()

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
        app.state.contracts_dir = directory
        app.state.monitor = monitor
        app.state.engine = engine
        app.state.contract_load_issues = issues
        app.state.ws_manager = ws_manager
        app.state.resource_lab = ResourceLabController()
        task: asyncio.Task[None] | None = None
        ws_broadcast_task: asyncio.Task[None] | None = None
        if auto_start:
            task = asyncio.create_task(engine.run_forever())

        async def ws_loop() -> None:
            while True:
                await asyncio.sleep(2.0)
                if ws_manager.active_connections:
                    try:
                        msg = websocket_state_payload(engine, "tick")
                        await ws_manager.broadcast(msg)
                    except Exception as e:
                        logger.debug("WS broadcast error: %s", e)

        ws_broadcast_task = asyncio.create_task(ws_loop())

        try:
            yield
        finally:
            if ws_broadcast_task is not None:
                ws_broadcast_task.cancel()
                try:
                    await ws_broadcast_task
                except asyncio.CancelledError:
                    pass
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            problems = engine.shutdown()
            for problem in problems:
                logger.error("shutdown restoration problem: %s", problem)
            app.state.resource_lab.close()

    app = FastAPI(
        title="ARC",
        description="Adaptive Resource Contract Engine API (reads engine state only)",
        lifespan=lifespan,
    )

    cors_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    cors_origins.extend(
        origin.strip()
        for origin in os.environ.get("ARC_CORS_ORIGINS", "").split(",")
        if origin.strip()
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
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
            cgroup_available=status.cgroup_available,
            cgroup_reason=status.cgroup_reason,
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
        statuses = [_contract_status_response(view) for view in engine.contract_statuses()]
        return ContractListResponse(
            contracts=statuses,
            count=len(statuses),
            load_errors=list(app.state.contract_load_issues),
        )

    @app.post("/api/contracts/validate", response_model=ValidateContractResponse)
    def validate_contract_payload(payload: dict = Body(...)) -> ValidateContractResponse:
        """Validate a contract payload without saving or affecting the engine."""
        try:
            contract = Contract.model_validate(payload)
            return ValidateContractResponse(valid=True, contract=contract, error=None)
        except Exception as exc:
            return ValidateContractResponse(valid=False, contract=None, error=str(exc))

    @app.post("/api/contracts", response_model=ContractStatus)
    def create_contract(contract: Contract) -> ContractStatus:
        """Create a new contract, write YAML atomically, and register with engine."""
        directory = app.state.contracts_dir
        engine: ObservationEngine = app.state.engine

        if any(c.id == contract.id for c in engine.contracts):
            raise HTTPException(
                status_code=409, detail=f"contract with id '{contract.id}' already exists"
            )

        try:
            save_contract_file(directory, contract)
        except ContractPersistenceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        engine.set_contract(contract)
        views = {v.contract.id: v for v in engine.contract_statuses()}
        view = views[contract.id]
        return _contract_status_response(view)

    @app.put("/api/contracts/{contract_id}", response_model=ContractStatus)
    def update_contract(
        contract_id: str = PathParam(..., description="ID of contract to update"),
        contract: Contract = Body(...),
    ) -> ContractStatus:
        """Update an existing contract. Rejects updates if contract is ACTIVE or RESTORING."""
        if contract.id != contract_id:
            raise HTTPException(
                status_code=400,
                detail=f"contract body id '{contract.id}' does not match path '{contract_id}'",
            )
        directory = app.state.contracts_dir
        engine: ObservationEngine = app.state.engine

        runtime = engine.runtime_for(contract_id)
        if runtime is not None and runtime.lifecycle in (
            LifecycleState.ACTIVE,
            LifecycleState.ACTIVATING,
            LifecycleState.RESTORING,
        ):
            detail_msg = (
                f"cannot update contract {contract_id} while in state {runtime.lifecycle.value}"
            )
            raise HTTPException(status_code=409, detail=detail_msg)

        try:
            save_contract_file(directory, contract)
        except ContractPersistenceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            engine.set_contract(contract)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        views = {v.contract.id: v for v in engine.contract_statuses()}
        view = views[contract.id]
        return _contract_status_response(view)

    @app.delete("/api/contracts/{contract_id}")
    def delete_contract(
        contract_id: str = PathParam(..., description="ID of contract to delete"),
    ) -> dict[str, str]:
        """Delete a contract. Rejects deletion if contract is currently ACTIVE or RESTORING."""
        directory = app.state.contracts_dir
        engine: ObservationEngine = app.state.engine

        runtime = engine.runtime_for(contract_id)
        if runtime is not None and runtime.lifecycle in (
            LifecycleState.ACTIVE,
            LifecycleState.ACTIVATING,
            LifecycleState.RESTORING,
        ):
            detail_msg = (
                f"cannot delete contract {contract_id} while in state {runtime.lifecycle.value}"
            )
            raise HTTPException(status_code=409, detail=detail_msg)

        try:
            delete_contract_file(directory, contract_id)
        except ContractPersistenceError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        # Reload the directory into the engine
        contracts, issues = load_contracts_lenient(directory)
        app.state.contract_load_issues = issues
        engine.reload_contracts(contracts)
        return {"status": "deleted", "contract_id": contract_id}

    @app.patch("/api/contracts/{contract_id}/enabled", response_model=ContractStatus)
    def toggle_contract_enabled(
        contract_id: str = PathParam(..., description="ID of contract to toggle"),
        payload: ToggleEnabledRequest = Body(...),
    ) -> ContractStatus:
        """Enable or disable a contract."""
        directory = app.state.contracts_dir
        engine: ObservationEngine = app.state.engine

        try:
            engine.enable_contract(
                contract_id,
                payload.enabled,
                persist=lambda contract: save_contract_file(directory, contract),
            )
        except KeyError:
            raise HTTPException(status_code=404, detail=f"contract {contract_id} not found")
        except ContractPersistenceError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        views = {v.contract.id: v for v in engine.contract_statuses()}
        view = views[contract_id]
        return _contract_status_response(view)

    @app.post("/api/contracts/{contract_id}/reset")
    def reset_contract_error(
        contract_id: str = PathParam(..., description="ID of contract to reset"),
    ) -> dict[str, str]:
        """Manually reset a latched ERROR contract back to INACTIVE."""
        engine: ObservationEngine = app.state.engine
        success = engine.reset_contract(contract_id)
        if not success:
            runtime = engine.runtime_for(contract_id)
            if runtime is not None and runtime.lifecycle is LifecycleState.ERROR:
                raise HTTPException(
                    status_code=409,
                    detail=runtime.last_error or f"contract {contract_id} recovery failed",
                )
            raise HTTPException(
                status_code=400,
                detail=f"contract {contract_id} is not in ERROR state or does not exist",
            )
        return {"status": "reset", "contract_id": contract_id}

    @app.post("/api/engine/reload")
    def reload_engine_contracts() -> dict[str, object]:
        """Reload all contract definitions from disk into the persistent engine."""
        directory = app.state.contracts_dir
        engine: ObservationEngine = app.state.engine
        contracts, issues = load_contracts_lenient(directory)
        app.state.contract_load_issues = issues
        try:
            engine.reload_contracts(contracts)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "status": "reloaded",
            "contract_count": len(contracts),
            "issues": [i.model_dump() for i in issues],
        }

    @app.get("/api/processes", response_model=ProcessListResponse)
    def get_processes(
        limit: int = Query(default=DEFAULT_PROCESS_LIMIT, ge=1, le=MAX_PROCESS_LIMIT),
    ) -> ProcessListResponse:
        """Latest engine process snapshot enriched with nice, affinity, and ARC-managed status."""
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
        managed_map = app.state.engine.managed_pids_by_contract()
        adapter: ResourceAdapter = app.state.engine.resource_adapter

        results: list[ProcessResponse] = []
        for obs in page:
            active_cids = managed_map.get(obs.pid, [])
            arc_managed = len(active_cids) > 0
            nice_val = None
            affinity_val = None
            try:
                nice_val = adapter.get_nice(obs.pid)
            except Exception:
                pass
            try:
                affinity_val = list(adapter.get_affinity(obs.pid))
            except Exception:
                pass

            results.append(
                ProcessResponse.from_observation(
                    obs,
                    nice=nice_val,
                    cpu_affinity=affinity_val,
                    arc_managed=arc_managed,
                    active_contract_ids=active_cids,
                )
            )

        return ProcessListResponse(
            processes=results,
            count=len(results),
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

    def resource_lab_payload() -> dict[str, object]:
        payload = app.state.resource_lab.status()
        view = next(
            (
                item
                for item in app.state.engine.contract_statuses()
                if item.contract.id == LAB_CONTRACT_ID
            ),
            None,
        )
        payload["contract"] = (
            _contract_status_response(view).model_dump(mode="json") if view is not None else None
        )
        return payload

    def install_resource_lab_contract(cpu: int) -> None:
        engine: ObservationEngine = app.state.engine
        contract = Contract.model_validate(
            {
                "version": 1,
                "id": LAB_CONTRACT_ID,
                "name": "Resource Lab CPU Contention",
                "description": "Isolate controlled background workers during sustained pressure.",
                "enabled": False,
                "target": {
                    "type": "process",
                    "match": {"command_contains": "arc-resource-lab-background"},
                },
                "trigger": {
                    "metric": "system.cpu.percent",
                    "operator": "gt",
                    "value": 20,
                    "for_seconds": 3,
                },
                "actions": [{"type": "cpu_affinity", "cpus": [cpu]}],
                "restore": {
                    "metric": "system.cpu.percent",
                    "operator": "lt",
                    "value": 10,
                    "for_seconds": 3,
                },
            }
        )
        existing = next((item for item in engine.contracts if item.id == LAB_CONTRACT_ID), None)
        if existing is not None and existing == contract:
            return
        try:
            engine.set_contract(contract)
            save_contract_file(app.state.contracts_dir, contract)
        except (ValueError, ContractPersistenceError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/resource-lab")
    def get_resource_lab() -> dict[str, object]:
        """Read current controlled workload measurements and policy state."""
        return resource_lab_payload()

    @app.post("/api/resource-lab/start")
    def start_resource_lab(request: ResourceLabStartRequest) -> dict[str, object]:
        """Start bounded ARC-owned workers and install the disabled demo contract."""
        try:
            state = app.state.resource_lab.start(request.workers)
            cpu = state.get("policy_cpu")
            if not isinstance(cpu, int):
                raise ResourceLabError("no usable policy CPU was detected")
            install_resource_lab_contract(cpu)
            return resource_lab_payload()
        except ResourceLabError as exc:
            app.state.resource_lab.stop()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except HTTPException:
            app.state.resource_lab.stop()
            raise

    @app.post("/api/resource-lab/pressure")
    def set_resource_lab_pressure(
        request: ResourceLabPressureRequest,
    ) -> dict[str, object]:
        """Switch real background workers between measured HIGH and LOW modes."""
        try:
            app.state.resource_lab.set_pressure(request.high)
            return resource_lab_payload()
        except ResourceLabError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/resource-lab/policy")
    def set_resource_lab_policy(payload: ToggleEnabledRequest) -> dict[str, object]:
        """Enable or disable the real Resource Lab contract through the engine."""
        try:
            app.state.engine.enable_contract(
                LAB_CONTRACT_ID,
                payload.enabled,
                persist=lambda contract: save_contract_file(app.state.contracts_dir, contract),
            )
            return resource_lab_payload()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="start the Resource Lab first") from exc
        except (ValueError, ContractPersistenceError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/resource-lab/stop")
    def stop_resource_lab() -> dict[str, object]:
        """Stop lab-owned workers only after ARC has released their resources."""
        runtime = app.state.engine.runtime_for(LAB_CONTRACT_ID)
        if runtime is not None and (
            runtime.lifecycle is not LifecycleState.INACTIVE or runtime.snapshots
        ):
            raise HTTPException(
                status_code=409,
                detail="lower pressure and wait for exact restoration before stopping the lab",
            )
        contract = next(
            (item for item in app.state.engine.contracts if item.id == LAB_CONTRACT_ID), None
        )
        if contract is not None and contract.enabled:
            app.state.engine.enable_contract(
                LAB_CONTRACT_ID,
                False,
                persist=lambda updated: save_contract_file(app.state.contracts_dir, updated),
            )
        app.state.resource_lab.stop()
        return resource_lab_payload()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """WebSocket for live state streaming (does not drive enforcement)."""
        manager: ConnectionManager = app.state.ws_manager
        await manager.connect(websocket)
        try:
            # Send initial state snapshot immediately
            engine: ObservationEngine = app.state.engine
            await websocket.send_json(websocket_state_payload(engine, "init"))
            while True:
                # Keep alive / read incoming pings
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception:
            manager.disconnect(websocket)

    return app


app = create_app()
