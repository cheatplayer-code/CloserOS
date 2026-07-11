"""Tests for CLS-011.2c authentication session domain entity."""

# mypy: disable-error-code=import-untyped

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.domain import (
    AuthenticationAssuranceLevel,
    AuthenticationSession,
    AuthenticationTokenHash,
)

SESSION_ID = UUID("00000000-0000-0000-0000-000000000100")
USER_ID = UUID("00000000-0000-0000-0000-000000000010")
TOKEN_HASH = AuthenticationTokenHash(digest=bytes(range(32)))
CREATED_AT = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
LAST_SEEN_AT = datetime(2026, 7, 11, 12, 15, 0, tzinfo=UTC)
EXPIRES_AT = datetime(2026, 7, 12, 0, 0, 0, tzinfo=UTC)
REVOKED_AT = datetime(2026, 7, 11, 13, 0, 0, tzinfo=UTC)


def _build_session(**overrides: object) -> AuthenticationSession:
    values = {
        "id": SESSION_ID,
        "user_id": USER_ID,
        "token_hash": TOKEN_HASH,
        "assurance_level": AuthenticationAssuranceLevel.MULTI_FACTOR,
        "mfa_completed": True,
        "created_at": CREATED_AT,
        "last_seen_at": LAST_SEEN_AT,
        "expires_at": EXPIRES_AT,
        "revoked_at": None,
    }
    values.update(overrides)
    return AuthenticationSession(**cast(Any, values))


def test_valid_active_session_stores_every_supplied_value() -> None:
    session = _build_session()

    assert session.id == SESSION_ID
    assert session.user_id == USER_ID
    assert session.token_hash is TOKEN_HASH
    assert session.assurance_level is AuthenticationAssuranceLevel.MULTI_FACTOR
    assert session.mfa_completed is True
    assert session.created_at == CREATED_AT
    assert session.last_seen_at == LAST_SEEN_AT
    assert session.expires_at == EXPIRES_AT
    assert session.revoked_at is None


def test_pending_mfa_session_is_accepted() -> None:
    session = _build_session(
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        mfa_completed=False,
    )

    assert session.assurance_level is AuthenticationAssuranceLevel.SINGLE_FACTOR
    assert session.mfa_completed is False


def test_multi_factor_session_with_mfa_completed_is_accepted() -> None:
    session = _build_session(
        assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
        mfa_completed=True,
    )

    assert session.assurance_level is AuthenticationAssuranceLevel.MULTI_FACTOR
    assert session.mfa_completed is True


def test_revoked_at_none_is_accepted() -> None:
    session = _build_session(revoked_at=None)

    assert session.revoked_at is None


def test_timezone_aware_revoked_at_is_accepted() -> None:
    session = _build_session(revoked_at=REVOKED_AT)

    assert session.revoked_at == REVOKED_AT


def test_token_hash_is_excluded_from_repr() -> None:
    session_repr = repr(_build_session())

    assert repr(TOKEN_HASH.digest) not in session_repr
    assert TOKEN_HASH.digest.hex() not in session_repr


def test_non_uuid_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="id must be a UUID"):
        _build_session(id=cast(Any, 123))


def test_non_uuid_user_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="user_id must be a UUID"):
        _build_session(user_id=cast(Any, "00000000-0000-0000-0000-000000000010"))


def test_plain_bytes_token_hash_raises_type_error() -> None:
    with pytest.raises(TypeError, match="token_hash must be an AuthenticationTokenHash"):
        _build_session(token_hash=cast(Any, bytes(range(32))))


def test_plain_string_assurance_level_raises_type_error() -> None:
    with pytest.raises(TypeError, match="assurance_level must be an AuthenticationAssuranceLevel"):
        _build_session(assurance_level=cast(Any, "multi_factor"))


def test_integer_mfa_completed_one_raises_type_error() -> None:
    with pytest.raises(TypeError, match="mfa_completed must be a bool"):
        _build_session(mfa_completed=cast(Any, 1))


def test_integer_mfa_completed_zero_raises_type_error() -> None:
    with pytest.raises(TypeError, match="mfa_completed must be a bool"):
        _build_session(mfa_completed=cast(Any, 0))


def test_non_datetime_created_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="created_at must be a datetime"):
        _build_session(created_at=cast(Any, "2026-07-11T12:00:00Z"))


def test_non_datetime_last_seen_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="last_seen_at must be a datetime"):
        _build_session(last_seen_at=cast(Any, "2026-07-11T12:15:00Z"))


def test_non_datetime_expires_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="expires_at must be a datetime"):
        _build_session(expires_at=cast(Any, "2026-07-12T00:00:00Z"))


def test_non_datetime_revoked_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="revoked_at must be a datetime"):
        _build_session(revoked_at=cast(Any, "2026-07-11T13:00:00Z"))


def test_naive_created_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        _build_session(created_at=datetime(2026, 7, 11, 12, 0, 0))


def test_naive_last_seen_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="last_seen_at must be timezone-aware"):
        _build_session(last_seen_at=datetime(2026, 7, 11, 12, 15, 0))


def test_naive_expires_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="expires_at must be timezone-aware"):
        _build_session(expires_at=datetime(2026, 7, 12, 0, 0, 0))


def test_naive_revoked_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="revoked_at must be timezone-aware"):
        _build_session(revoked_at=datetime(2026, 7, 11, 13, 0, 0))


def test_last_seen_at_before_created_at_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="last_seen_at must be greater than or equal to created_at",
    ):
        _build_session(last_seen_at=CREATED_AT - timedelta(minutes=1))


def test_expires_at_equal_to_created_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="expires_at must be strictly greater than created_at"):
        _build_session(expires_at=CREATED_AT)


def test_expires_at_before_created_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="expires_at must be strictly greater than created_at"):
        _build_session(expires_at=CREATED_AT - timedelta(hours=1))


def test_last_seen_at_after_expires_at_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="last_seen_at must be less than or equal to expires_at",
    ):
        _build_session(last_seen_at=EXPIRES_AT + timedelta(minutes=1))


def test_revoked_at_before_created_at_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="revoked_at must be greater than or equal to created_at",
    ):
        _build_session(revoked_at=CREATED_AT - timedelta(minutes=1))


def test_authentication_session_can_be_imported_from_closeros_domain() -> None:
    assert AuthenticationSession.__name__ == "AuthenticationSession"
