"""Tests for CLS-011.3c authentication session timeout policy."""

# mypy: disable-error-code=import-untyped

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from closeros.domain import (
    AUTHENTICATION_SESSION_TIMEOUT_POLICY,
    AuthenticationSessionStage,
    AuthenticationSessionTimeoutPolicy,
    calculate_authentication_session_absolute_expiry,
    calculate_authentication_session_idle_expiry,
)

CREATED_AT = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
LAST_SEEN_AT = datetime(2026, 7, 11, 12, 15, 0, tzinfo=UTC)
CUSTOM_IDLE_TIMEOUT = timedelta(minutes=7)
CUSTOM_ABSOLUTE_TIMEOUT = timedelta(hours=3)
CUSTOM_PENDING_MFA_TIMEOUT = timedelta(minutes=2)


def _custom_policy() -> AuthenticationSessionTimeoutPolicy:
    return AuthenticationSessionTimeoutPolicy(
        authenticated_idle_timeout=CUSTOM_IDLE_TIMEOUT,
        authenticated_absolute_timeout=CUSTOM_ABSOLUTE_TIMEOUT,
        pending_mfa_timeout=CUSTOM_PENDING_MFA_TIMEOUT,
    )


def test_canonical_authenticated_idle_timeout_is_exactly_30_minutes() -> None:
    assert AUTHENTICATION_SESSION_TIMEOUT_POLICY.authenticated_idle_timeout == timedelta(minutes=30)


def test_canonical_authenticated_absolute_timeout_is_exactly_12_hours() -> None:
    assert AUTHENTICATION_SESSION_TIMEOUT_POLICY.authenticated_absolute_timeout == timedelta(
        hours=12
    )


def test_canonical_pending_mfa_timeout_is_exactly_5_minutes() -> None:
    assert AUTHENTICATION_SESSION_TIMEOUT_POLICY.pending_mfa_timeout == timedelta(minutes=5)


def test_valid_custom_policy_is_accepted() -> None:
    policy = _custom_policy()

    assert policy.authenticated_idle_timeout == CUSTOM_IDLE_TIMEOUT
    assert policy.authenticated_absolute_timeout == CUSTOM_ABSOLUTE_TIMEOUT
    assert policy.pending_mfa_timeout == CUSTOM_PENDING_MFA_TIMEOUT


def test_policy_stores_supplied_timedeltas_unchanged() -> None:
    policy = _custom_policy()

    assert policy.authenticated_idle_timeout is CUSTOM_IDLE_TIMEOUT
    assert policy.authenticated_absolute_timeout is CUSTOM_ABSOLUTE_TIMEOUT
    assert policy.pending_mfa_timeout is CUSTOM_PENDING_MFA_TIMEOUT


def test_policy_is_immutable_and_assignment_raises_frozen_instance_error() -> None:
    policy = _custom_policy()

    with pytest.raises(FrozenInstanceError):
        cast(Any, policy).authenticated_idle_timeout = timedelta(minutes=1)


def test_non_timedelta_authenticated_idle_timeout_raises_type_error() -> None:
    with pytest.raises(TypeError, match="authenticated_idle_timeout must be a timedelta"):
        AuthenticationSessionTimeoutPolicy(
            authenticated_idle_timeout=cast(Any, 30),
            authenticated_absolute_timeout=timedelta(hours=12),
            pending_mfa_timeout=timedelta(minutes=5),
        )


def test_non_timedelta_authenticated_absolute_timeout_raises_type_error() -> None:
    with pytest.raises(
        TypeError,
        match="authenticated_absolute_timeout must be a timedelta",
    ):
        AuthenticationSessionTimeoutPolicy(
            authenticated_idle_timeout=timedelta(minutes=30),
            authenticated_absolute_timeout=cast(Any, 12),
            pending_mfa_timeout=timedelta(minutes=5),
        )


def test_non_timedelta_pending_mfa_timeout_raises_type_error() -> None:
    with pytest.raises(TypeError, match="pending_mfa_timeout must be a timedelta"):
        AuthenticationSessionTimeoutPolicy(
            authenticated_idle_timeout=timedelta(minutes=30),
            authenticated_absolute_timeout=timedelta(hours=12),
            pending_mfa_timeout=cast(Any, 5),
        )


def test_zero_authenticated_idle_timeout_raises_value_error() -> None:
    with pytest.raises(ValueError, match="authenticated_idle_timeout must be greater than zero"):
        AuthenticationSessionTimeoutPolicy(
            authenticated_idle_timeout=timedelta(0),
            authenticated_absolute_timeout=timedelta(hours=12),
            pending_mfa_timeout=timedelta(minutes=5),
        )


def test_negative_authenticated_idle_timeout_raises_value_error() -> None:
    with pytest.raises(ValueError, match="authenticated_idle_timeout must be greater than zero"):
        AuthenticationSessionTimeoutPolicy(
            authenticated_idle_timeout=timedelta(minutes=-1),
            authenticated_absolute_timeout=timedelta(hours=12),
            pending_mfa_timeout=timedelta(minutes=5),
        )


def test_zero_authenticated_absolute_timeout_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="authenticated_absolute_timeout must be greater than zero",
    ):
        AuthenticationSessionTimeoutPolicy(
            authenticated_idle_timeout=timedelta(minutes=30),
            authenticated_absolute_timeout=timedelta(0),
            pending_mfa_timeout=timedelta(minutes=5),
        )


def test_negative_authenticated_absolute_timeout_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="authenticated_absolute_timeout must be greater than zero",
    ):
        AuthenticationSessionTimeoutPolicy(
            authenticated_idle_timeout=timedelta(minutes=30),
            authenticated_absolute_timeout=timedelta(hours=-1),
            pending_mfa_timeout=timedelta(minutes=5),
        )


def test_zero_pending_mfa_timeout_raises_value_error() -> None:
    with pytest.raises(ValueError, match="pending_mfa_timeout must be greater than zero"):
        AuthenticationSessionTimeoutPolicy(
            authenticated_idle_timeout=timedelta(minutes=30),
            authenticated_absolute_timeout=timedelta(hours=12),
            pending_mfa_timeout=timedelta(0),
        )


def test_negative_pending_mfa_timeout_raises_value_error() -> None:
    with pytest.raises(ValueError, match="pending_mfa_timeout must be greater than zero"):
        AuthenticationSessionTimeoutPolicy(
            authenticated_idle_timeout=timedelta(minutes=30),
            authenticated_absolute_timeout=timedelta(hours=12),
            pending_mfa_timeout=timedelta(minutes=-1),
        )


def test_pending_mfa_absolute_expiry_is_created_at_plus_5_minutes() -> None:
    expiry = calculate_authentication_session_absolute_expiry(
        stage=AuthenticationSessionStage.PENDING_MFA,
        created_at=CREATED_AT,
    )

    assert expiry == CREATED_AT + timedelta(minutes=5)


def test_authenticated_absolute_expiry_is_created_at_plus_12_hours() -> None:
    expiry = calculate_authentication_session_absolute_expiry(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        created_at=CREATED_AT,
    )

    assert expiry == CREATED_AT + timedelta(hours=12)


def test_pending_mfa_idle_expiry_is_none() -> None:
    expiry = calculate_authentication_session_idle_expiry(
        stage=AuthenticationSessionStage.PENDING_MFA,
        last_seen_at=LAST_SEEN_AT,
    )

    assert expiry is None


def test_authenticated_idle_expiry_is_last_seen_at_plus_30_minutes() -> None:
    expiry = calculate_authentication_session_idle_expiry(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        last_seen_at=LAST_SEEN_AT,
    )

    assert expiry == LAST_SEEN_AT + timedelta(minutes=30)


def test_custom_policy_controls_all_calculated_deadlines() -> None:
    policy = _custom_policy()

    pending_absolute = calculate_authentication_session_absolute_expiry(
        stage=AuthenticationSessionStage.PENDING_MFA,
        created_at=CREATED_AT,
        policy=policy,
    )
    authenticated_absolute = calculate_authentication_session_absolute_expiry(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        created_at=CREATED_AT,
        policy=policy,
    )
    pending_idle = calculate_authentication_session_idle_expiry(
        stage=AuthenticationSessionStage.PENDING_MFA,
        last_seen_at=LAST_SEEN_AT,
        policy=policy,
    )
    authenticated_idle = calculate_authentication_session_idle_expiry(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        last_seen_at=LAST_SEEN_AT,
        policy=policy,
    )

    assert pending_absolute == CREATED_AT + CUSTOM_PENDING_MFA_TIMEOUT
    assert authenticated_absolute == CREATED_AT + CUSTOM_ABSOLUTE_TIMEOUT
    assert pending_idle is None
    assert authenticated_idle == LAST_SEEN_AT + CUSTOM_IDLE_TIMEOUT


def test_string_stage_raises_type_error_in_absolute_expiry_calculation() -> None:
    with pytest.raises(TypeError, match="stage must be an AuthenticationSessionStage"):
        calculate_authentication_session_absolute_expiry(
            stage=cast(Any, "pending_mfa"),
            created_at=CREATED_AT,
        )


def test_string_stage_raises_type_error_in_idle_expiry_calculation() -> None:
    with pytest.raises(TypeError, match="stage must be an AuthenticationSessionStage"):
        calculate_authentication_session_idle_expiry(
            stage=cast(Any, "authenticated"),
            last_seen_at=LAST_SEEN_AT,
        )


def test_non_datetime_created_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="created_at must be a datetime"):
        calculate_authentication_session_absolute_expiry(
            stage=AuthenticationSessionStage.AUTHENTICATED,
            created_at=cast(Any, "2026-07-11T12:00:00Z"),
        )


def test_naive_created_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        calculate_authentication_session_absolute_expiry(
            stage=AuthenticationSessionStage.AUTHENTICATED,
            created_at=datetime(2026, 7, 11, 12, 0, 0),
        )


def test_non_datetime_last_seen_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="last_seen_at must be a datetime"):
        calculate_authentication_session_idle_expiry(
            stage=AuthenticationSessionStage.AUTHENTICATED,
            last_seen_at=cast(Any, "2026-07-11T12:15:00Z"),
        )


def test_naive_last_seen_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="last_seen_at must be timezone-aware"):
        calculate_authentication_session_idle_expiry(
            stage=AuthenticationSessionStage.AUTHENTICATED,
            last_seen_at=datetime(2026, 7, 11, 12, 15, 0),
        )


def test_wrong_policy_type_raises_type_error_in_absolute_calculation() -> None:
    with pytest.raises(
        TypeError,
        match="policy must be an AuthenticationSessionTimeoutPolicy",
    ):
        calculate_authentication_session_absolute_expiry(
            stage=AuthenticationSessionStage.AUTHENTICATED,
            created_at=CREATED_AT,
            policy=cast(Any, object()),
        )


def test_wrong_policy_type_raises_type_error_in_idle_calculation() -> None:
    with pytest.raises(
        TypeError,
        match="policy must be an AuthenticationSessionTimeoutPolicy",
    ):
        calculate_authentication_session_idle_expiry(
            stage=AuthenticationSessionStage.AUTHENTICATED,
            last_seen_at=LAST_SEEN_AT,
            policy=cast(Any, object()),
        )


def test_calculations_do_not_mutate_custom_policy() -> None:
    policy = _custom_policy()
    before = (
        policy.authenticated_idle_timeout,
        policy.authenticated_absolute_timeout,
        policy.pending_mfa_timeout,
    )

    calculate_authentication_session_absolute_expiry(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        created_at=CREATED_AT,
        policy=policy,
    )
    calculate_authentication_session_idle_expiry(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        last_seen_at=LAST_SEEN_AT,
        policy=policy,
    )

    after = (
        policy.authenticated_idle_timeout,
        policy.authenticated_absolute_timeout,
        policy.pending_mfa_timeout,
    )
    assert after == before


def test_calculations_do_not_mutate_supplied_datetime_values() -> None:
    created_at = CREATED_AT
    last_seen_at = LAST_SEEN_AT
    created_before = created_at
    last_seen_before = last_seen_at

    calculate_authentication_session_absolute_expiry(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        created_at=created_at,
    )
    calculate_authentication_session_idle_expiry(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        last_seen_at=last_seen_at,
    )

    assert created_at is created_before
    assert last_seen_at is last_seen_before


def test_public_symbols_can_be_imported_from_closeros_domain() -> None:
    assert AuthenticationSessionTimeoutPolicy.__name__ == "AuthenticationSessionTimeoutPolicy"
    assert AUTHENTICATION_SESSION_TIMEOUT_POLICY.__class__ is AuthenticationSessionTimeoutPolicy
    assert (
        calculate_authentication_session_absolute_expiry.__name__
        == "calculate_authentication_session_absolute_expiry"
    )
    assert (
        calculate_authentication_session_idle_expiry.__name__
        == "calculate_authentication_session_idle_expiry"
    )
