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
