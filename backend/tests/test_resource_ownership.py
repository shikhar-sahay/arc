"""Resource-level ownership prevents contracts from overtaking each other."""

from arc.contracts.models import Contract
from arc.core.lifecycle import EvaluationOutcome, LifecycleState
from tests.conftest import make_contract, make_engine, make_observation, make_telemetry


def _contract(
    contract_id: str,
    action: dict[str, object],
    *,
    trigger_metric: str = "system.cpu.percent",
) -> Contract:
    return make_contract(
        id=contract_id,
        name=contract_id,
        trigger={
            "metric": trigger_metric,
            "operator": "gt",
            "value": 50,
            "for_seconds": 0,
        },
        actions=[action],
        restore={
            "metric": "system.cpu.percent",
            "operator": "lt",
            "value": 20,
            "for_seconds": 0,
        },
    )


def test_same_resource_activation_is_deferred_until_owner_restores() -> None:
    first = _contract("first-nice", {"type": "nice", "value": 5})
    second = _contract(
        "second-nice",
        {"type": "nice", "value": 10},
        trigger_metric="system.memory.percent",
    )
    engine, adapter = make_engine([first, second])
    observations = [make_observation()]

    activated = engine.step(make_telemetry(cpu=80, memory=80), observations, now=0)

    assert activated.evaluations[0].outcome is EvaluationOutcome.ACTIVATED
    assert activated.evaluations[1].outcome is EvaluationOutcome.RESOURCE_CONFLICT
    assert engine.runtime_for("first-nice").lifecycle is LifecycleState.ACTIVE
    assert engine.runtime_for("second-nice").lifecycle is LifecycleState.INACTIVE
    assert adapter.get_nice(50) == 5
    assert adapter.set_calls_for("set_nice", 50) == [5]

    handoff = engine.step(make_telemetry(cpu=10, memory=80), observations, now=1)

    assert handoff.evaluations[0].outcome is EvaluationOutcome.RESTORED
    assert handoff.evaluations[1].outcome is EvaluationOutcome.ACTIVATED
    assert adapter.set_calls_for("set_nice", 50) == [5, 0, 10]
    assert adapter.get_nice(50) == 10


def test_different_resources_can_be_owned_on_same_process() -> None:
    nice = _contract("nice-owner", {"type": "nice", "value": 7})
    affinity = _contract(
        "affinity-owner",
        {"type": "cpu_affinity", "cpus": [1]},
        trigger_metric="system.memory.percent",
    )
    engine, adapter = make_engine([nice, affinity])

    result = engine.step(make_telemetry(cpu=80, memory=80), [make_observation()], now=0)

    assert [evaluation.outcome for evaluation in result.evaluations] == [
        EvaluationOutcome.ACTIVATED,
        EvaluationOutcome.ACTIVATED,
    ]
    assert adapter.get_nice(50) == 7
    assert adapter.get_affinity(50) == (1,)


def test_suspend_and_resume_share_process_state_ownership() -> None:
    suspend = _contract("suspend-owner", {"type": "suspend"})
    resume = _contract(
        "resume-owner",
        {"type": "resume"},
        trigger_metric="system.memory.percent",
    )
    engine, adapter = make_engine([suspend, resume])

    result = engine.step(make_telemetry(cpu=80, memory=80), [make_observation()], now=0)

    assert result.evaluations[0].outcome is EvaluationOutcome.ACTIVATED
    assert result.evaluations[1].outcome is EvaluationOutcome.RESOURCE_CONFLICT
    assert adapter.is_stopped(50) is True


def test_failed_restoration_retains_ownership_until_recovery() -> None:
    first = _contract("first-nice", {"type": "nice", "value": 5})
    second = _contract(
        "second-nice",
        {"type": "nice", "value": 10},
        trigger_metric="system.memory.percent",
    )
    engine, adapter = make_engine([first, second])
    observations = [make_observation()]
    engine.step(make_telemetry(cpu=80, memory=10), observations, now=0)
    adapter.deny_on("set_nice", 50)

    failed = engine.step(make_telemetry(cpu=10, memory=80), observations, now=1)

    assert failed.evaluations[0].outcome is EvaluationOutcome.RESTORATION_ERROR
    assert failed.evaluations[1].outcome is EvaluationOutcome.RESOURCE_CONFLICT
    assert engine.runtime_for("first-nice").lifecycle is LifecycleState.ERROR
    assert engine.runtime_for("first-nice").snapshots
    assert adapter.set_calls_for("set_nice", 50) == [5]

    adapter.deny_sets.clear()
    assert engine.reset_contract("first-nice") is True
    assert engine.runtime_for("first-nice").snapshots == []
    assert adapter.get_nice(50) == 0

    retried = engine.step(make_telemetry(cpu=10, memory=80), observations, now=2)
    assert retried.evaluations[1].outcome is EvaluationOutcome.ACTIVATED
    assert adapter.get_nice(50) == 10
