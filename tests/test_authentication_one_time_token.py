"""Tests for CLS-011.2d one-time authentication token domain entity."""

# mypy: disable-error-code=import-untyped

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.domain import (
    AuthenticationOneTimeToken,
    AuthenticationTokenHash,
    AuthenticationTokenPurpose,
)

TOKEN_ID = UUID("00000000-0000-0000-0000-000000000200")
USER_ID = UUID("00000000-0000-0000-0000-000000000010")
TOKEN_HASH = AuthenticationTokenHash(digest=bytes(range(32)))
CREATED_AT = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
EXPIRES_AT = datetime(2026, 7, 11, 13, 0, 0, tzinfo=UTC)
CONSUMED_AT = datetime(2026, 7, 11, 12, 30, 0, tzinfo=UTC)
REVOKED_AT = datetime(2026, 7, 11, 12, 45, 0, tzinfo=UTC)


def _build_token(**overrides: object) -> AuthenticationOneTimeToken:
    values = {
        "id": TOKEN_ID,
        "user_id": USER_ID,
        "purpose": AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        "token_hash": TOKEN_HASH,
        "created_at": CREATED_AT,
        "expires_at": EXPIRES_AT,
        "consumed_at": None,
        "revoked_at": None,
    }
    values.update(overrides)
    return AuthenticationOneTimeToken(**cast(Any, values))


def test_valid_email_verification_token_is_accepted() -> None:
    token = _build_token(purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION)

    assert token.purpose is AuthenticationTokenPurpose.EMAIL_VERIFICATION


def test_valid_password_reset_token_is_accepted() -> None:
    token = _build_token(purpose=AuthenticationTokenPurpose.PASSWORD_RESET)

    assert token.purpose is AuthenticationTokenPurpose.PASSWORD_RESET


def test_consumed_at_none_is_accepted() -> None:
    token = _build_token(consumed_at=None)

    assert token.consumed_at is None


def test_timezone_aware_consumed_at_is_accepted() -> None:
    token = _build_token(consumed_at=CONSUMED_AT)

    assert token.consumed_at == CONSUMED_AT


def test_revoked_at_none_is_accepted() -> None:
    token = _build_token(revoked_at=None)

    assert token.revoked_at is None


def test_timezone_aware_revoked_at_is_accepted() -> None:
    token = _build_token(revoked_at=REVOKED_AT)

    assert token.revoked_at == REVOKED_AT


def test_consumed_at_and_revoked_at_may_both_be_present() -> None:
    token = _build_token(consumed_at=CONSUMED_AT, revoked_at=REVOKED_AT)

    assert token.consumed_at == CONSUMED_AT
    assert token.revoked_at == REVOKED_AT


def test_token_hash_is_excluded_from_repr() -> None:
    token_repr = repr(_build_token())

    assert repr(TOKEN_HASH.digest) not in token_repr
    assert TOKEN_HASH.digest.hex() not in token_repr


def test_non_uuid_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="id must be a UUID"):
        _build_token(id=cast(Any, 123))


def test_non_uuid_user_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="user_id must be a UUID"):
        _build_token(user_id=cast(Any, "00000000-0000-0000-0000-000000000010"))


def test_string_purpose_raises_type_error() -> None:
    with pytest.raises(TypeError, match="purpose must be an AuthenticationTokenPurpose"):
        _build_token(purpose=cast(Any, "email_verification"))


def test_plain_bytes_token_hash_raises_type_error() -> None:
    with pytest.raises(TypeError, match="token_hash must be an AuthenticationTokenHash"):
        _build_token(token_hash=cast(Any, bytes(range(32))))


def test_non_datetime_created_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="created_at must be a datetime"):
        _build_token(created_at=cast(Any, "2026-07-11T12:00:00Z"))


def test_non_datetime_expires_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="expires_at must be a datetime"):
        _build_token(expires_at=cast(Any, "2026-07-11T13:00:00Z"))


def test_non_datetime_consumed_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="consumed_at must be a datetime"):
        _build_token(consumed_at=cast(Any, "2026-07-11T12:30:00Z"))


def test_non_datetime_revoked_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="revoked_at must be a datetime"):
        _build_token(revoked_at=cast(Any, "2026-07-11T12:45:00Z"))


def test_naive_created_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        _build_token(created_at=datetime(2026, 7, 11, 12, 0, 0))


def test_naive_expires_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="expires_at must be timezone-aware"):
        _build_token(expires_at=datetime(2026, 7, 11, 13, 0, 0))


def test_naive_consumed_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="consumed_at must be timezone-aware"):
        _build_token(consumed_at=datetime(2026, 7, 11, 12, 30, 0))


def test_naive_revoked_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="revoked_at must be timezone-aware"):
        _build_token(revoked_at=datetime(2026, 7, 11, 12, 45, 0))


def test_expires_at_equal_to_created_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="expires_at must be strictly greater than created_at"):
        _build_token(expires_at=CREATED_AT)


def test_expires_at_before_created_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="expires_at must be strictly greater than created_at"):
        _build_token(expires_at=CREATED_AT - timedelta(hours=1))


def test_consumed_at_before_created_at_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="consumed_at must be greater than or equal to created_at",
    ):
        _build_token(consumed_at=CREATED_AT - timedelta(minutes=1))


def test_consumed_at_after_expires_at_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="consumed_at must be less than or equal to expires_at",
    ):
        _build_token(consumed_at=EXPIRES_AT + timedelta(minutes=1))


def test_revoked_at_before_created_at_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="revoked_at must be greater than or equal to created_at",
    ):
        _build_token(revoked_at=CREATED_AT - timedelta(minutes=1))


def test_authentication_one_time_token_can_be_imported_from_closeros_domain() -> None:
    assert AuthenticationOneTimeToken.__name__ == "AuthenticationOneTimeToken"
