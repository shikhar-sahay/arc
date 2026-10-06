"""Read-only observation and evaluation engine.

The engine loads contracts, collects telemetry and process snapshots,
resolves targets, and evaluates triggers while maintaining duration
state across polling cycles. It never executes actions and never
modifies the OS.

Nothing starts a loop on import. Callers drive ``poll()`` explicitly or
await ``run_forever()``.
"""

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from arc.contracts.models import Contract
from arc.core.lifecycle import ContractRuntimeState, EvaluationOutcome
from arc.evaluation.service import ContractEvaluation, evaluate_contract
from arc.monitoring.processes import ProcessObservation, sample_processes
from arc.monitoring.system import SystemMonitor, SystemSnapshot

logger = logging.getLogger(__name__)


@dataclass
class EngineCycle:
    """Everything observed and decided in one polling cycle."""

    telemetry: SystemSnapshot
    process_count: int
    evaluations: list[ContractEvaluation] = field(default_factory=list)


class ObservationEngine:
    """Polls the system and evaluates contracts without enforcing."""

    def __init__(
        self,
        contracts: Sequence[Contract] = (),
        poll_interval_seconds: float = 5.0,
        system_monitor: SystemMonitor | None = None,
        process_sampler: Callable[[], list[ProcessObservation]] | None = None,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._contracts = list(contracts)
        self.poll_interval_seconds = poll_interval_seconds
        self._monitor = system_monitor or SystemMonitor()
        self._process_sampler = process_sampler or sample_processes
        self._runtimes = {
            contract.id: ContractRuntimeState(contract_id=contract.id)
            for contract in self._contracts
        }
        for contract in self._contracts:
            runtime = self._runtimes[contract.id]
            runtime.trigger_tracker.required_seconds = contract.trigger.for_seconds
            runtime.restore_tracker.required_seconds = contract.restore.for_seconds

    @property
    def contracts(self) -> list[Contract]:
        """Loaded contract definitions (configuration, not runtime state)."""
        return list(self._contracts)

    def runtime_for(self, contract_id: str) -> ContractRuntimeState | None:
        """Transient runtime state for one contract, if known."""
        return self._runtimes.get(contract_id)

    def evaluate_snapshot(
        self,
        telemetry: SystemSnapshot,
        observations: list[ProcessObservation],
        now: float,
    ) -> list[ContractEvaluation]:
        """Evaluate all contracts against injected snapshots (test hook)."""
        results: list[ContractEvaluation] = []
        for contract in self._contracts:
            runtime = self._runtimes[contract.id]
            previous = runtime.last_outcome
            result = evaluate_contract(contract, telemetry, observations, runtime, now)
            self._log_transition(contract.id, previous, result)
            results.append(result)
        return results

    def poll(self) -> EngineCycle:
        """Collect one live snapshot and evaluate every contract."""
        telemetry = self._monitor.sample()
        observations = self._process_sampler()
        now = time.monotonic()
        evaluations = self.evaluate_snapshot(telemetry, observations, now)
        return EngineCycle(
            telemetry=telemetry,
            process_count=len(observations),
            evaluations=evaluations,
        )

    async def run_forever(self) -> None:
        """Poll on ``poll_interval_seconds`` until cancelled."""
        while True:
            self.poll()
            await asyncio.sleep(self.poll_interval_seconds)

    def _log_transition(
        self,
        contract_id: str,
        previous: EvaluationOutcome | None,
        result: ContractEvaluation,
    ) -> None:
        changed = previous != result.outcome
        if result.outcome is EvaluationOutcome.WOULD_ACTIVATE and changed:
            logger.info("contract %s trigger satisfied: %s", contract_id, result.detail)
        elif result.outcome is EvaluationOutcome.EVALUATION_ERROR and changed:
            logger.warning("contract %s evaluation error: %s", contract_id, result.error)
        elif changed:
            logger.debug("contract %s: %s", contract_id, result.detail)
