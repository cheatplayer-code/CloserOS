"""Tests for CLS-011.2k authentication session usability guard."""

# mypy: disable-error-code=import-untyped

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.domain import (
    AuthenticationAssuranceLevel,
    AuthenticationSession,
    AuthenticationSessionUnavailableError,
    AuthenticationTokenHash,
    require_usable_authentication_session,
)

SESSION_ID = UUID("00000000-0000-0000-0000-000000000100")
USER_ID = UUID("00000000-0000-0000-0000-000000000010")
TOKEN_HASH = AuthenticationTokenHash(digest=bytes(range(32)))
CREATED_AT = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
LAST_SEEN_AT = datetime(2026, 7, 11, 12, 15, 0, tzinfo=UTC)
EXPIRES_AT = datetime(2026, 7, 12, 0, 0, 0, tzinfo=UTC)
REVOKED_AT = datetime(2026, 7, 11, 13, 0, 0, tzinfo=UTC)
FUTURE_REVOKED_AT = datetime(2026, 7, 11, 14, 0, 0, tzinfo=UTC)
NOW_WITHIN_VALIDITY = datetime(2026, 7, 11, 12, 30, 0, tzinfo=UTC)
DENIED_MESSAGE = "authentication session unavailable"


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


def test_active_single_factor_session_is_allowed() -> None:
    session = _build_session(
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        mfa_completed=False,
    )

    require_usable_authentication_session(session=session, now=NOW_WITHIN_VALIDITY)


def test_active_multi_factor_session_is_allowed() -> None:
    session = _build_session(
        assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
        mfa_completed=True,
    )

    require_usable_authentication_session(session=session, now=NOW_WITHIN_VALIDITY)


def test_allowed_call_returns_none() -> None:
    session = _build_session()
    require_usable_authentication_session_any: Any = require_usable_authentication_session

    assert (
        require_usable_authentication_session_any(
            session=session,
            now=NOW_WITHIN_VALIDITY,
        )
        is None
    )


def test_now_equal_to_created_at_and_last_seen_at_is_allowed() -> None:
    session = _build_session(
        last_seen_at=CREATED_AT,
    )

    require_usable_authentication_session(session=session, now=CREATED_AT)


def test_now_equal_to_last_seen_at_is_allowed() -> None:
    session = _build_session()

    require_usable_authentication_session(session=session, now=LAST_SEEN_AT)


def test_now_one_microsecond_before_expires_at_is_allowed() -> None:
    session = _build_session()

    require_usable_authentication_session(
        session=session,
        now=EXPIRES_AT - timedelta(microseconds=1),
    )


def test_now_equal_to_expires_at_is_denied() -> None:
    session = _build_session()

    with pytest.raises(
        AuthenticationSessionUnavailableError,
        match=f"^{DENIED_MESSAGE}$",
    ):
        require_usable_authentication_session(session=session, now=EXPIRES_AT)


def test_now_after_expires_at_is_denied() -> None:
    session = _build_session()

    with pytest.raises(
        AuthenticationSessionUnavailableError,
        match=f"^{DENIED_MESSAGE}$",
    ):
        require_usable_authentication_session(
            session=session,
            now=EXPIRES_AT + timedelta(seconds=1),
        )


def test_now_before_created_at_is_denied() -> None:
    session = _build_session()

    with pytest.raises(
        AuthenticationSessionUnavailableError,
        match=f"^{DENIED_MESSAGE}$",
    ):
        require_usable_authentication_session(
            session=session,
            now=CREATED_AT - timedelta(seconds=1),
        )


def test_now_before_last_seen_at_is_denied() -> None:
    session = _build_session()

    with pytest.raises(
        AuthenticationSessionUnavailableError,
        match=f"^{DENIED_MESSAGE}$",
    ):
        require_usable_authentication_session(
            session=session,
            now=LAST_SEEN_AT - timedelta(seconds=1),
        )


def test_revoked_session_is_denied() -> None:
    session = _build_session(revoked_at=REVOKED_AT)

    with pytest.raises(
        AuthenticationSessionUnavailableError,
        match=f"^{DENIED_MESSAGE}$",
    ):
        require_usable_authentication_session(session=session, now=NOW_WITHIN_VALIDITY)


def test_session_with_future_revoked_at_is_still_denied() -> None:
    session = _build_session(revoked_at=FUTURE_REVOKED_AT)

    with pytest.raises(
        AuthenticationSessionUnavailableError,
        match=f"^{DENIED_MESSAGE}$",
    ):
        require_usable_authentication_session(session=session, now=NOW_WITHIN_VALIDITY)


@pytest.mark.parametrize(
    "now",
    [
        CREATED_AT - timedelta(seconds=1),
        LAST_SEEN_AT - timedelta(seconds=1),
        EXPIRES_AT,
        EXPIRES_AT + timedelta(seconds=1),
    ],
)
def test_every_denial_raises_authentication_session_unavailable_error(
    now: datetime,
) -> None:
    session = _build_session()

    with pytest.raises(AuthenticationSessionUnavailableError):
        require_usable_authentication_session(session=session, now=now)


@pytest.mark.parametrize(
    "now",
    [
        CREATED_AT - timedelta(seconds=1),
        LAST_SEEN_AT - timedelta(seconds=1),
        EXPIRES_AT,
        EXPIRES_AT + timedelta(seconds=1),
    ],
)
def test_every_denial_uses_exact_denial_message(now: datetime) -> None:
    session = _build_session()

    with pytest.raises(
        AuthenticationSessionUnavailableError,
        match=f"^{DENIED_MESSAGE}$",
    ) as exc_info:
        require_usable_authentication_session(session=session, now=now)

    assert str(exc_info.value) == DENIED_MESSAGE


def test_denial_message_and_repr_contain_no_sensitive_details() -> None:
    session = _build_session(revoked_at=REVOKED_AT)

    with pytest.raises(AuthenticationSessionUnavailableError) as exc_info:
        require_usable_authentication_session(session=session, now=NOW_WITHIN_VALIDITY)

    error_text = f"{exc_info.value}{repr(exc_info.value)}"
    assert str(SESSION_ID) not in error_text
    assert str(USER_ID) not in error_text
    assert repr(TOKEN_HASH.digest) not in error_text
    assert TOKEN_HASH.digest.hex() not in error_text
    assert AuthenticationAssuranceLevel.MULTI_FACTOR.value not in error_text
    assert CREATED_AT.isoformat() not in error_text
    assert LAST_SEEN_AT.isoformat() not in error_text
    assert EXPIRES_AT.isoformat() not in error_text
    assert REVOKED_AT.isoformat() not in error_text


def test_wrong_session_argument_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="session must be an AuthenticationSession"):
        require_usable_authentication_session(
            session=cast(Any, object()),
            now=NOW_WITHIN_VALIDITY,
        )


def test_wrong_now_argument_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="now must be a datetime"):
        require_usable_authentication_session(
            session=_build_session(),
            now=cast(Any, "2026-07-11T12:30:00Z"),
        )


def test_naive_now_raises_value_error() -> None:
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        require_usable_authentication_session(
            session=_build_session(),
            now=datetime(2026, 7, 11, 12, 30, 0),
        )


def test_policy_does_not_mutate_allowed_session() -> None:
    session = _build_session()
    before = (
        session.id,
        session.user_id,
        session.token_hash,
        session.assurance_level,
        session.mfa_completed,
        session.created_at,
        session.last_seen_at,
        session.expires_at,
        session.revoked_at,
    )

    require_usable_authentication_session(session=session, now=NOW_WITHIN_VALIDITY)

    after = (
        session.id,
        session.user_id,
        session.token_hash,
        session.assurance_level,
        session.mfa_completed,
        session.created_at,
        session.last_seen_at,
        session.expires_at,
        session.revoked_at,
    )
    assert after == before


def test_policy_does_not_mutate_denied_session() -> None:
    session = _build_session(revoked_at=REVOKED_AT)
    before = (
        session.id,
        session.user_id,
        session.token_hash,
        session.assurance_level,
        session.mfa_completed,
        session.created_at,
        session.last_seen_at,
        session.expires_at,
        session.revoked_at,
    )

    with pytest.raises(AuthenticationSessionUnavailableError):
        require_usable_authentication_session(session=session, now=NOW_WITHIN_VALIDITY)

    after = (
        session.id,
        session.user_id,
        session.token_hash,
        session.assurance_level,
        session.mfa_completed,
        session.created_at,
        session.last_seen_at,
        session.expires_at,
        session.revoked_at,
    )
    assert after == before


def test_authentication_session_policy_symbols_can_be_imported_from_closeros_domain() -> None:
    assert AuthenticationSessionUnavailableError.__name__ == "AuthenticationSessionUnavailableError"
    assert require_usable_authentication_session.__name__ == "require_usable_authentication_session"
