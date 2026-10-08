"""Tests for dynamic contract reload and lifecycle protection."""

import pytest

from arc.core.lifecycle import LifecycleState
from tests.conftest import make_contract, make_engine


def test_reload_contracts_atomic() -> None:
    c1 = make_contract(id="c1", name="Contract 1")
    c2 = make_contract(id="c2", name="Contract 2")
    engine, _ = make_engine(contracts=[c1])

    assert len(engine.contracts) == 1
    assert engine.runtime_for("c1") is not None

    # Reload with c1 updated and c2 added
    c1_updated = make_contract(id="c1", name="Contract 1 Updated")
    engine.reload_contracts([c1_updated, c2])

    assert len(engine.contracts) == 2
    assert engine.contracts[0].name == "Contract 1 Updated"
    assert engine.runtime_for("c2") is not None


def test_reload_protects_active_contract() -> None:
    c1 = make_contract(id="c1")
    engine, _ = make_engine(contracts=[c1])
    runtime = engine.runtime_for("c1")
    assert runtime is not None
    runtime.transition_to(LifecycleState.ACTIVATING)
    runtime.transition_to(LifecycleState.ACTIVE)

    # Attempting to reload without c1 should fail
    with pytest.raises(ValueError, match="cannot remove contract c1"):
        engine.reload_contracts([])


@pytest.mark.parametrize(
    "state",
    [LifecycleState.ACTIVATING, LifecycleState.ACTIVE, LifecycleState.RESTORING],
)
def test_reload_rejects_changed_protected_contract_atomically(state) -> None:
    trigger = {
        "metric": "system.cpu.percent",
        "operator": "gt",
        "value": 75,
        "for_seconds": 7,
    }
    original = make_contract(id="c1", name="Original", trigger=trigger)
    engine, _ = make_engine(contracts=[original])
    runtime = engine.runtime_for("c1")
    assert runtime is not None
    runtime.lifecycle = state

    changed = make_contract(id="c1", name="Changed", trigger={**trigger, "for_seconds": 99})
    with pytest.raises(ValueError, match="cannot modify contract c1"):
        engine.reload_contracts([changed])

    assert engine.contracts == [original]
    assert runtime.trigger_tracker.required_seconds == 7


@pytest.mark.parametrize(
    "state",
    [LifecycleState.ACTIVATING, LifecycleState.ACTIVE, LifecycleState.RESTORING],
)
def test_reload_accepts_unchanged_protected_contract(state) -> None:
    original = make_contract(id="c1")
    engine, _ = make_engine(contracts=[original])
    runtime = engine.runtime_for("c1")
    assert runtime is not None
    runtime.lifecycle = state

    engine.reload_contracts([original.model_copy(deep=True)])

    assert engine.contracts == [original]
    assert engine.runtime_for("c1") is runtime


def test_reload_allows_inactive_definition_update() -> None:
    original = make_contract(id="c1", name="Original")
    changed = make_contract(id="c1", name="Changed")
    engine, _ = make_engine(contracts=[original])

    engine.reload_contracts([changed])

    assert engine.contracts == [changed]


def test_reload_protects_error_contract_with_recoverable_snapshot() -> None:
    from arc.linux.resources import ResourceSnapshot

    original = make_contract(id="c1")
    engine, fake = make_engine(contracts=[original])
    runtime = engine.runtime_for("c1")
    assert runtime is not None
    runtime.lifecycle = LifecycleState.ERROR
    runtime.snapshots = [ResourceSnapshot(identity=fake.get_identity(50), nice=0)]

    with pytest.raises(ValueError, match="cannot remove contract c1"):
        engine.reload_contracts([])

    assert engine.contracts == [original]
    assert runtime.snapshots


def test_set_contract_protects_active_contract() -> None:
    c1 = make_contract(id="c1")
    engine, _ = make_engine(contracts=[c1])
    runtime = engine.runtime_for("c1")
    assert runtime is not None
    runtime.transition_to(LifecycleState.ACTIVATING)
    runtime.transition_to(LifecycleState.ACTIVE)

    c1_mod = make_contract(id="c1", name="Modified")
    with pytest.raises(ValueError, match="cannot modify contract c1"):
        engine.set_contract(c1_mod)


def test_enable_contract_toggle() -> None:
    c1 = make_contract(id="c1", enabled=True)
    engine, _ = make_engine(contracts=[c1])

    updated = engine.enable_contract("c1", False)
    assert updated.enabled is False
    assert engine.contracts[0].enabled is False

    updated2 = engine.enable_contract("c1", True)
    assert updated2.enabled is True
    assert engine.contracts[0].enabled is True


@pytest.mark.parametrize(
    "state",
    [LifecycleState.ACTIVATING, LifecycleState.ACTIVE, LifecycleState.RESTORING],
)
def test_enable_contract_rejects_protected_states(state) -> None:
    c1 = make_contract(id="c1", enabled=True)
    engine, _ = make_engine(contracts=[c1])
    runtime = engine.runtime_for("c1")
    assert runtime is not None
    runtime.lifecycle = state

    with pytest.raises(ValueError, match="cannot change enabled state"):
        engine.enable_contract("c1", False)

    assert engine.contracts[0].enabled is True


def test_enable_contract_persistence_failure_is_atomic() -> None:
    c1 = make_contract(id="c1", enabled=True)
    engine, _ = make_engine(contracts=[c1])

    def fail(_contract) -> None:
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError, match="disk full"):
        engine.enable_contract("c1", False, persist=fail)

    assert engine.contracts[0].enabled is True
