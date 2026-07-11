"""Tests for CLS-010.3c retention policy value object."""

from dataclasses import FrozenInstanceError

import pytest
from closeros.domain import RetentionPolicy

VALID_POLICY_VALUES = {
    "raw_message_days": 30,
    "sanitized_message_days": 30,
    "ai_output_days": 30,
    "audit_log_days": 365,
    "backup_days": 30,
    "post_contract_deletion_days": 90,
}

RETENTION_FIELDS = tuple(VALID_POLICY_VALUES.keys())


def test_valid_positive_values_are_stored() -> None:
    policy = RetentionPolicy(**VALID_POLICY_VALUES)

    assert policy.raw_message_days == 30
    assert policy.sanitized_message_days == 30
    assert policy.ai_output_days == 30
    assert policy.audit_log_days == 365
    assert policy.backup_days == 30
    assert policy.post_contract_deletion_days == 90


def test_zero_is_accepted_for_every_field() -> None:
    policy = RetentionPolicy(0, 0, 0, 0, 0, 0)

    assert policy.raw_message_days == 0
    assert policy.sanitized_message_days == 0
    assert policy.ai_output_days == 0
    assert policy.audit_log_days == 0
    assert policy.backup_days == 0
    assert policy.post_contract_deletion_days == 0


@pytest.mark.parametrize("field_name", RETENTION_FIELDS)
def test_each_field_rejects_negative_value(field_name: str) -> None:
    values = VALID_POLICY_VALUES.copy()
    values[field_name] = -1

    with pytest.raises(ValueError, match=f"{field_name} must be greater than or equal to zero"):
        RetentionPolicy(**values)


@pytest.mark.parametrize("field_name", RETENTION_FIELDS)
def test_each_field_rejects_string_value(field_name: str) -> None:
    values = VALID_POLICY_VALUES.copy()
    values[field_name] = "30"  # type: ignore[assignment]

    with pytest.raises(TypeError, match=f"{field_name} must be an int"):
        RetentionPolicy(**values)


@pytest.mark.parametrize("field_name", RETENTION_FIELDS)
def test_each_field_rejects_bool_value(field_name: str) -> None:
    values = VALID_POLICY_VALUES.copy()
    values[field_name] = True  # type: ignore[assignment]

    with pytest.raises(TypeError, match=f"{field_name} must be an int"):
        RetentionPolicy(**values)


def test_retention_policy_is_immutable() -> None:
    policy = RetentionPolicy(**VALID_POLICY_VALUES)

    with pytest.raises(FrozenInstanceError):
        policy.raw_message_days = 10  # type: ignore[misc]


def test_retention_policy_can_be_imported_from_closeros_domain() -> None:
    assert RetentionPolicy.__name__ == "RetentionPolicy"
