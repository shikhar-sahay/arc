"""Tests for the authoritative contract domain model."""

import pytest
from pydantic import ValidationError

from arc.contracts.models import Contract
from tests.conftest import valid_contract_data


def test_valid_contract_parses() -> None:
    """A complete, well formed contract validates."""
    contract = Contract.model_validate(valid_contract_data())

    assert contract.id == "compile-relief"
    assert contract.version == 1
    assert contract.enabled is True
    assert len(contract.actions) == 1


def test_all_action_types_parse() -> None:
    """All four planned action types validate together."""
    contract = Contract.model_validate(
        valid_contract_data(
            actions=[
                {"type": "nice", "value": 10},
                {"type": "cpu_affinity", "cpus": [0, 1]},
                {"type": "suspend"},
                {"type": "resume"},
            ]
        )
    )

    assert len(contract.actions) == 4


@pytest.mark.parametrize(
    "bad_id",
    ["Bad ID!", "-leading", "trailing-", "", "has space", "UPPER", "under_score", "a" * 65],
)
def test_invalid_contract_ids_rejected(bad_id: str) -> None:
    """IDs must be conservative slugs for filenames and logs."""
    with pytest.raises(ValidationError):
        Contract.model_validate(valid_contract_data(id=bad_id))


def test_missing_actions_rejected() -> None:
    """A contract with no actions is meaningless and rejected."""
    with pytest.raises(ValidationError):
        Contract.model_validate(valid_contract_data(actions=[]))


@pytest.mark.parametrize("value", [-21, 20, 100])
def test_nice_value_outside_linux_range_rejected(value: int) -> None:
    """Nice values must fit the Linux range of -20 to 19."""
    with pytest.raises(ValidationError):
        Contract.model_validate(valid_contract_data(actions=[{"type": "nice", "value": value}]))


def test_empty_affinity_cpu_list_rejected() -> None:
    """An empty CPU list would constrain the process to nothing."""
    with pytest.raises(ValidationError):
        Contract.model_validate(valid_contract_data(actions=[{"type": "cpu_affinity", "cpus": []}]))


def test_duplicate_affinity_cpus_rejected() -> None:
    """Duplicate CPU indexes are a configuration mistake."""
    with pytest.raises(ValidationError):
        Contract.model_validate(
            valid_contract_data(actions=[{"type": "cpu_affinity", "cpus": [0, 0, 1]}])
        )


def test_negative_affinity_cpu_rejected() -> None:
    """CPU indexes must be non-negative."""
    with pytest.raises(ValidationError):
        Contract.model_validate(
            valid_contract_data(actions=[{"type": "cpu_affinity", "cpus": [0, -1]}])
        )


def test_unknown_action_type_rejected() -> None:
    """Action types are a closed set in this pass."""
    with pytest.raises(ValidationError):
        Contract.model_validate(valid_contract_data(actions=[{"type": "overclock", "value": 99}]))


def test_numeric_metric_with_boolean_operator_rejected() -> None:
    """CPU percent needs a numeric operator, not a boolean one."""
    with pytest.raises(ValidationError):
        Contract.model_validate(
            valid_contract_data(
                trigger={"metric": "system.cpu.percent", "operator": "bogus", "value": 75}
            )
        )


def test_numeric_metric_with_boolean_value_rejected() -> None:
    """CPU percent needs a numeric threshold."""
    with pytest.raises(ValidationError):
        Contract.model_validate(
            valid_contract_data(
                trigger={"metric": "system.cpu.percent", "operator": "gt", "value": True}
            )
        )


def test_presence_metric_with_numeric_operator_rejected() -> None:
    """Process presence only supports eq and ne."""
    with pytest.raises(ValidationError):
        Contract.model_validate(
            valid_contract_data(
                trigger={"metric": "target.process.present", "operator": "gt", "value": True}
            )
        )


def test_presence_metric_with_non_boolean_value_rejected() -> None:
    """Process presence needs a boolean value."""
    with pytest.raises(ValidationError):
        Contract.model_validate(
            valid_contract_data(
                trigger={"metric": "target.process.present", "operator": "eq", "value": 1}
            )
        )


@pytest.mark.parametrize("metric", ["system.cpu.percent", "system.memory.percent"])
@pytest.mark.parametrize("value", [-1, 101, 500])
def test_out_of_range_metric_value_rejected(metric: str, value: float) -> None:
    """Percentage metrics only accept 0 to 100."""
    with pytest.raises(ValidationError):
        Contract.model_validate(
            valid_contract_data(trigger={"metric": metric, "operator": "gt", "value": value})
        )


def test_negative_duration_rejected() -> None:
    """for_seconds cannot be negative."""
    with pytest.raises(ValidationError):
        Contract.model_validate(
            valid_contract_data(
                trigger={
                    "metric": "system.cpu.percent",
                    "operator": "gt",
                    "value": 75,
                    "for_seconds": -1,
                }
            )
        )


def test_missing_restore_condition_rejected() -> None:
    """Every contract needs a restoration condition for hysteresis."""
    data = valid_contract_data()
    del data["restore"]
    with pytest.raises(ValidationError):
        Contract.model_validate(data)


def test_empty_process_match_rejected() -> None:
    """A target with no criteria would match every process."""
    with pytest.raises(ValidationError):
        Contract.model_validate(valid_contract_data(target={"type": "process", "match": {}}))


def test_unknown_version_rejected() -> None:
    """Only schema version 1 exists in this pass."""
    with pytest.raises(ValidationError):
        Contract.model_validate(valid_contract_data(version=2))


def test_unknown_top_level_field_rejected() -> None:
    """Typos in field names fail loudly instead of being ignored."""
    with pytest.raises(ValidationError):
        Contract.model_validate(valid_contract_data(triger="typo"))
