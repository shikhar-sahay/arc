"""Read-only contract evaluation, independent of FastAPI.

Evaluation answers whether a trigger condition holds and for how long,
using an injected monotonic clock value so tests advance time without
sleeping. Satisfied triggers yield ``WOULD_ACTIVATE`` (a preview), never
a claim that enforcement happened.
"""

import logging
from dataclasses import dataclass, field

from arc.contracts.models import (
    BooleanOperator,
    Condition,
    Contract,
    MetricName,
    NumericOperator,
)
from arc.core.lifecycle import (
    ContractRuntimeState,
    DurationTracker,
    EvaluationOutcome,
    LifecycleState,
)
from arc.monitoring.processes import ProcessObservation, resolve_process_target
from arc.monitoring.system import SystemSnapshot

logger = logging.getLogger(__name__)


class ConditionEvaluationError(Exception):
    """A condition could not be evaluated against a snapshot."""


@dataclass(frozen=True)
class ConditionEvaluation:
    """Result of one condition check at one point in time."""

    raw: bool
    satisfied: bool
    elapsed_seconds: float
    required_seconds: float


@dataclass
class ContractEvaluation:
    """Read-only evaluation result for one contract in one cycle."""

    contract_id: str
    outcome: EvaluationOutcome
    trigger_raw: bool | None = None
    trigger_satisfied: bool | None = None
    matched_pids: list[int] = field(default_factory=list)
    detail: str = ""
    error: str | None = None


def _compare_numeric(operator: NumericOperator, actual: float, expected: float) -> bool:
    if operator is NumericOperator.GT:
        return actual > expected
    if operator is NumericOperator.GTE:
        return actual >= expected
    if operator is NumericOperator.LT:
        return actual < expected
    if operator is NumericOperator.LTE:
        return actual <= expected
    if operator is NumericOperator.EQ:
        return actual == expected
    return actual != expected


def evaluate_condition_raw(
    condition: Condition,
    telemetry: SystemSnapshot,
    matched: list[ProcessObservation],
) -> bool:
    """Evaluate the raw comparison, ignoring duration requirements."""
    if condition.metric is MetricName.SYSTEM_CPU_PERCENT:
        return _compare_numeric(
            NumericOperator(condition.operator),
            telemetry.cpu_percent,
            float(condition.value),
        )
    if condition.metric is MetricName.SYSTEM_MEMORY_PERCENT:
        return _compare_numeric(
            NumericOperator(condition.operator),
            telemetry.memory_percent,
            float(condition.value),
        )
    if condition.metric is MetricName.TARGET_PROCESS_PRESENT:
        present = len(matched) > 0
        expected = bool(condition.value)
        if BooleanOperator(condition.operator) is BooleanOperator.EQ:
            return present == expected
        return present != expected
    raise ConditionEvaluationError(f"unsupported metric: {condition.metric}")


def evaluate_condition(
    condition: Condition,
    telemetry: SystemSnapshot,
    matched: list[ProcessObservation],
    tracker: DurationTracker,
    now: float,
) -> ConditionEvaluation:
    """Evaluate a condition including its ``for_seconds`` duration."""
    raw = evaluate_condition_raw(condition, telemetry, matched)
    satisfied = tracker.update(raw, now)
    return ConditionEvaluation(
        raw=raw,
        satisfied=satisfied,
        elapsed_seconds=tracker.elapsed(now),
        required_seconds=tracker.required_seconds,
    )


def evaluate_contract(
    contract: Contract,
    telemetry: SystemSnapshot,
    observations: list[ProcessObservation],
    runtime: ContractRuntimeState,
    now: float,
) -> ContractEvaluation:
    """Evaluate one contract trigger against a snapshot. Read-only."""
    if not contract.enabled:
        runtime.note_evaluated(EvaluationOutcome.DISABLED, now)
        return ContractEvaluation(
            contract_id=contract.id,
            outcome=EvaluationOutcome.DISABLED,
            detail="contract is disabled",
        )
    try:
        matched = resolve_process_target(contract.target, observations)
    except Exception as exc:
        message = f"target resolution failed: {exc}"
        logger.warning("contract %s: %s", contract.id, message)
        runtime.lifecycle = LifecycleState.ERROR
        runtime.last_error = message
        runtime.note_evaluated(EvaluationOutcome.EVALUATION_ERROR, now)
        return ContractEvaluation(
            contract_id=contract.id,
            outcome=EvaluationOutcome.EVALUATION_ERROR,
            error=message,
            detail=message,
        )
    runtime.matched_pids = [obs.pid for obs in matched]
    if not matched:
        runtime.trigger_tracker.reset()
        runtime.note_evaluated(EvaluationOutcome.TARGET_NOT_FOUND, now)
        return ContractEvaluation(
            contract_id=contract.id,
            outcome=EvaluationOutcome.TARGET_NOT_FOUND,
            trigger_raw=None,
            trigger_satisfied=False,
            detail="no running process matches the contract target",
        )
    try:
        result = evaluate_condition(
            contract.trigger, telemetry, matched, runtime.trigger_tracker, now
        )
    except (ConditionEvaluationError, ValueError) as exc:
        message = f"trigger evaluation failed: {exc}"
        logger.warning("contract %s: %s", contract.id, message)
        runtime.lifecycle = LifecycleState.ERROR
        runtime.last_error = message
        runtime.note_evaluated(EvaluationOutcome.EVALUATION_ERROR, now)
        return ContractEvaluation(
            contract_id=contract.id,
            outcome=EvaluationOutcome.EVALUATION_ERROR,
            matched_pids=runtime.matched_pids,
            error=message,
            detail=message,
        )
    if result.satisfied:
        outcome = EvaluationOutcome.WOULD_ACTIVATE
        detail = (
            f"trigger holds for {len(matched)} matched process(es), "
            "contract would activate once enforcement exists"
        )
    else:
        outcome = EvaluationOutcome.TRIGGER_PENDING
        detail = (
            f"trigger raw={result.raw} "
            f"({result.elapsed_seconds:.1f}s of {result.required_seconds:.1f}s)"
        )
    runtime.note_evaluated(outcome, now)
    return ContractEvaluation(
        contract_id=contract.id,
        outcome=outcome,
        trigger_raw=result.raw,
        trigger_satisfied=result.satisfied,
        matched_pids=runtime.matched_pids,
        detail=detail,
    )
