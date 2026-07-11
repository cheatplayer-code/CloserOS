"""Tests for CLS-011.3f one-time authentication token timeout policy."""

# mypy: disable-error-code=import-untyped

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from closeros.domain import (
    AUTHENTICATION_ONE_TIME_TOKEN_TIMEOUT_POLICY,
    AuthenticationOneTimeTokenTimeoutPolicy,
    AuthenticationTokenPurpose,
    calculate_authentication_one_time_token_expiry,
)

CREATED_AT = datetime(2026, 7, 11, 12, 34, 56, 789123, tzinfo=UTC)
CUSTOM_EMAIL_VERIFICATION_TIMEOUT = timedelta(hours=6)
CUSTOM_PASSWORD_RESET_TIMEOUT = timedelta(minutes=15)


def _custom_policy() -> AuthenticationOneTimeTokenTimeoutPolicy:
    return AuthenticationOneTimeTokenTimeoutPolicy(
        email_verification_timeout=CUSTOM_EMAIL_VERIFICATION_TIMEOUT,
        password_reset_timeout=CUSTOM_PASSWORD_RESET_TIMEOUT,
    )


def test_canonical_email_verification_timeout_is_exactly_24_hours() -> None:
    assert AUTHENTICATION_ONE_TIME_TOKEN_TIMEOUT_POLICY.email_verification_timeout == timedelta(
        hours=24
    )


def test_canonical_password_reset_timeout_is_exactly_30_minutes() -> None:
    assert AUTHENTICATION_ONE_TIME_TOKEN_TIMEOUT_POLICY.password_reset_timeout == timedelta(
        minutes=30
    )


def test_valid_custom_policy_is_accepted() -> None:
    policy = _custom_policy()

    assert policy.email_verification_timeout == CUSTOM_EMAIL_VERIFICATION_TIMEOUT
    assert policy.password_reset_timeout == CUSTOM_PASSWORD_RESET_TIMEOUT


def test_custom_policy_stores_supplied_timedeltas_unchanged() -> None:
    policy = _custom_policy()

    assert policy.email_verification_timeout is CUSTOM_EMAIL_VERIFICATION_TIMEOUT
    assert policy.password_reset_timeout is CUSTOM_PASSWORD_RESET_TIMEOUT


def test_policy_is_immutable_and_assignment_raises_frozen_instance_error() -> None:
    policy = _custom_policy()

    with pytest.raises(FrozenInstanceError):
        cast(Any, policy).email_verification_timeout = timedelta(hours=1)


def test_non_timedelta_email_verification_timeout_raises_type_error() -> None:
    with pytest.raises(
        TypeError,
        match="email_verification_timeout must be a timedelta",
    ):
        AuthenticationOneTimeTokenTimeoutPolicy(
            email_verification_timeout=cast(Any, 24),
            password_reset_timeout=timedelta(minutes=30),
        )


def test_non_timedelta_password_reset_timeout_raises_type_error() -> None:
    with pytest.raises(
        TypeError,
        match="password_reset_timeout must be a timedelta",
    ):
        AuthenticationOneTimeTokenTimeoutPolicy(
            email_verification_timeout=timedelta(hours=24),
            password_reset_timeout=cast(Any, 30),
        )


def test_zero_email_verification_timeout_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="email_verification_timeout must be greater than zero",
    ):
        AuthenticationOneTimeTokenTimeoutPolicy(
            email_verification_timeout=timedelta(0),
            password_reset_timeout=timedelta(minutes=30),
        )


def test_negative_email_verification_timeout_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="email_verification_timeout must be greater than zero",
    ):
        AuthenticationOneTimeTokenTimeoutPolicy(
            email_verification_timeout=timedelta(hours=-1),
            password_reset_timeout=timedelta(minutes=30),
        )


def test_zero_password_reset_timeout_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="password_reset_timeout must be greater than zero",
    ):
        AuthenticationOneTimeTokenTimeoutPolicy(
            email_verification_timeout=timedelta(hours=24),
            password_reset_timeout=timedelta(0),
        )


def test_negative_password_reset_timeout_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="password_reset_timeout must be greater than zero",
    ):
        AuthenticationOneTimeTokenTimeoutPolicy(
            email_verification_timeout=timedelta(hours=24),
            password_reset_timeout=timedelta(minutes=-1),
        )


def test_email_verification_expiry_is_created_at_plus_24_hours() -> None:
    expiry = calculate_authentication_one_time_token_expiry(
        purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        created_at=CREATED_AT,
    )

    assert expiry == CREATED_AT + timedelta(hours=24)


def test_password_reset_expiry_is_created_at_plus_30_minutes() -> None:
    expiry = calculate_authentication_one_time_token_expiry(
        purpose=AuthenticationTokenPurpose.PASSWORD_RESET,
        created_at=CREATED_AT,
    )

    assert expiry == CREATED_AT + timedelta(minutes=30)


def test_custom_policy_controls_email_verification_expiry() -> None:
    policy = _custom_policy()

    expiry = calculate_authentication_one_time_token_expiry(
        purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        created_at=CREATED_AT,
        policy=policy,
    )

    assert expiry == CREATED_AT + CUSTOM_EMAIL_VERIFICATION_TIMEOUT


def test_custom_policy_controls_password_reset_expiry() -> None:
    policy = _custom_policy()

    expiry = calculate_authentication_one_time_token_expiry(
        purpose=AuthenticationTokenPurpose.PASSWORD_RESET,
        created_at=CREATED_AT,
        policy=policy,
    )

    assert expiry == CREATED_AT + CUSTOM_PASSWORD_RESET_TIMEOUT


def test_calculation_preserves_timezone() -> None:
    expiry = calculate_authentication_one_time_token_expiry(
        purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        created_at=CREATED_AT,
    )

    assert expiry.tzinfo is UTC
    assert expiry.utcoffset() == CREATED_AT.utcoffset()


def test_calculation_preserves_seconds_and_microseconds() -> None:
    expiry = calculate_authentication_one_time_token_expiry(
        purpose=AuthenticationTokenPurpose.PASSWORD_RESET,
        created_at=CREATED_AT,
    )

    assert expiry.second == CREATED_AT.second
    assert expiry.microsecond == CREATED_AT.microsecond


def test_string_purpose_raises_type_error() -> None:
    with pytest.raises(
        TypeError,
        match="purpose must be an AuthenticationTokenPurpose",
    ):
        calculate_authentication_one_time_token_expiry(
            purpose=cast(Any, "email_verification"),
            created_at=CREATED_AT,
        )


def test_non_datetime_created_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="created_at must be a datetime"):
        calculate_authentication_one_time_token_expiry(
            purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
            created_at=cast(Any, "2026-07-11T12:34:56Z"),
        )


def test_naive_created_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        calculate_authentication_one_time_token_expiry(
            purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
            created_at=datetime(2026, 7, 11, 12, 34, 56, 789123),
        )


def test_wrong_policy_type_raises_type_error() -> None:
    with pytest.raises(
        TypeError,
        match="policy must be an AuthenticationOneTimeTokenTimeoutPolicy",
    ):
        calculate_authentication_one_time_token_expiry(
            purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
            created_at=CREATED_AT,
            policy=cast(Any, object()),
        )


def test_calculation_does_not_mutate_created_at() -> None:
    created_at = CREATED_AT
    created_before = created_at

    calculate_authentication_one_time_token_expiry(
        purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        created_at=created_at,
    )

    assert created_at is created_before


def test_calculation_does_not_mutate_custom_policy() -> None:
    policy = _custom_policy()
    before = (
        policy.email_verification_timeout,
        policy.password_reset_timeout,
    )

    calculate_authentication_one_time_token_expiry(
        purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        created_at=CREATED_AT,
        policy=policy,
    )
    calculate_authentication_one_time_token_expiry(
        purpose=AuthenticationTokenPurpose.PASSWORD_RESET,
        created_at=CREATED_AT,
        policy=policy,
    )

    after = (
        policy.email_verification_timeout,
        policy.password_reset_timeout,
    )
    assert after == before


def test_authentication_one_time_token_timeout_policy_is_importable_from_domain() -> None:
    assert (
        AuthenticationOneTimeTokenTimeoutPolicy.__name__
        == "AuthenticationOneTimeTokenTimeoutPolicy"
    )


def test_authentication_one_time_token_timeout_policy_constant_is_importable() -> None:
    assert (
        AUTHENTICATION_ONE_TIME_TOKEN_TIMEOUT_POLICY.__class__
        is AuthenticationOneTimeTokenTimeoutPolicy
    )


def test_calculate_authentication_one_time_token_expiry_is_importable() -> None:
    assert (
        calculate_authentication_one_time_token_expiry.__name__
        == "calculate_authentication_one_time_token_expiry"
    )
