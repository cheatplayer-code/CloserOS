"""Tests for CLS-011.2j one-time authentication token usability guard."""

# mypy: disable-error-code=import-untyped

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.domain import (
    AuthenticationOneTimeToken,
    AuthenticationTokenHash,
    AuthenticationTokenPurpose,
    AuthenticationTokenUnavailableError,
    require_usable_authentication_token,
)

TOKEN_ID = UUID("00000000-0000-0000-0000-000000000200")
USER_ID = UUID("00000000-0000-0000-0000-000000000010")
TOKEN_HASH = AuthenticationTokenHash(digest=bytes(range(32)))
CREATED_AT = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
EXPIRES_AT = datetime(2026, 7, 11, 13, 0, 0, tzinfo=UTC)
CONSUMED_AT = datetime(2026, 7, 11, 12, 30, 0, tzinfo=UTC)
REVOKED_AT = datetime(2026, 7, 11, 12, 45, 0, tzinfo=UTC)
NOW_WITHIN_VALIDITY = datetime(2026, 7, 11, 12, 15, 0, tzinfo=UTC)
DENIED_MESSAGE = "authentication token unavailable"


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


def test_unconsumed_unrevoked_email_verification_token_before_expiry_is_allowed() -> None:
    token = _build_token(purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION)

    require_usable_authentication_token(token=token, now=NOW_WITHIN_VALIDITY)


def test_unconsumed_unrevoked_password_reset_token_before_expiry_is_allowed() -> None:
    token = _build_token(purpose=AuthenticationTokenPurpose.PASSWORD_RESET)

    require_usable_authentication_token(token=token, now=NOW_WITHIN_VALIDITY)


def test_allowed_call_returns_none() -> None:
    token = _build_token()
    require_usable_authentication_token_any: Any = require_usable_authentication_token

    assert (
        require_usable_authentication_token_any(
            token=token,
            now=NOW_WITHIN_VALIDITY,
        )
        is None
    )


def test_now_equal_to_created_at_is_allowed() -> None:
    token = _build_token()

    require_usable_authentication_token(token=token, now=CREATED_AT)


def test_now_one_microsecond_before_expires_at_is_allowed() -> None:
    token = _build_token()

    require_usable_authentication_token(
        token=token,
        now=EXPIRES_AT - timedelta(microseconds=1),
    )


def test_now_equal_to_expires_at_is_denied() -> None:
    token = _build_token()

    with pytest.raises(AuthenticationTokenUnavailableError, match=f"^{DENIED_MESSAGE}$"):
        require_usable_authentication_token(token=token, now=EXPIRES_AT)


def test_now_after_expires_at_is_denied() -> None:
    token = _build_token()

    with pytest.raises(AuthenticationTokenUnavailableError, match=f"^{DENIED_MESSAGE}$"):
        require_usable_authentication_token(
            token=token,
            now=EXPIRES_AT + timedelta(seconds=1),
        )


def test_now_before_created_at_is_denied() -> None:
    token = _build_token()

    with pytest.raises(AuthenticationTokenUnavailableError, match=f"^{DENIED_MESSAGE}$"):
        require_usable_authentication_token(
            token=token,
            now=CREATED_AT - timedelta(seconds=1),
        )


def test_consumed_token_is_denied() -> None:
    token = _build_token(consumed_at=CONSUMED_AT)

    with pytest.raises(AuthenticationTokenUnavailableError, match=f"^{DENIED_MESSAGE}$"):
        require_usable_authentication_token(token=token, now=NOW_WITHIN_VALIDITY)


def test_revoked_token_is_denied() -> None:
    token = _build_token(revoked_at=REVOKED_AT)

    with pytest.raises(AuthenticationTokenUnavailableError, match=f"^{DENIED_MESSAGE}$"):
        require_usable_authentication_token(token=token, now=NOW_WITHIN_VALIDITY)


def test_token_with_both_consumed_at_and_revoked_at_is_denied() -> None:
    token = _build_token(consumed_at=CONSUMED_AT, revoked_at=REVOKED_AT)

    with pytest.raises(AuthenticationTokenUnavailableError, match=f"^{DENIED_MESSAGE}$"):
        require_usable_authentication_token(token=token, now=NOW_WITHIN_VALIDITY)


@pytest.mark.parametrize(
    "now",
    [
        CREATED_AT - timedelta(seconds=1),
        EXPIRES_AT,
        EXPIRES_AT + timedelta(seconds=1),
    ],
)
def test_every_policy_denial_raises_authentication_token_unavailable_error(
    now: datetime,
) -> None:
    token = _build_token()

    with pytest.raises(AuthenticationTokenUnavailableError):
        require_usable_authentication_token(token=token, now=now)


@pytest.mark.parametrize(
    "now",
    [
        CREATED_AT - timedelta(seconds=1),
        EXPIRES_AT,
        EXPIRES_AT + timedelta(seconds=1),
    ],
)
def test_every_policy_denial_uses_exact_denial_message(now: datetime) -> None:
    token = _build_token()

    with pytest.raises(
        AuthenticationTokenUnavailableError,
        match=f"^{DENIED_MESSAGE}$",
    ) as exc_info:
        require_usable_authentication_token(token=token, now=now)

    assert str(exc_info.value) == DENIED_MESSAGE


def test_denial_message_and_repr_contain_no_sensitive_details() -> None:
    token = _build_token(consumed_at=CONSUMED_AT)

    with pytest.raises(AuthenticationTokenUnavailableError) as exc_info:
        require_usable_authentication_token(token=token, now=NOW_WITHIN_VALIDITY)

    error_text = f"{exc_info.value}{repr(exc_info.value)}"
    assert str(TOKEN_ID) not in error_text
    assert str(USER_ID) not in error_text
    assert AuthenticationTokenPurpose.EMAIL_VERIFICATION.value not in error_text
    assert repr(TOKEN_HASH.digest) not in error_text
    assert TOKEN_HASH.digest.hex() not in error_text
    assert CREATED_AT.isoformat() not in error_text
    assert EXPIRES_AT.isoformat() not in error_text


def test_wrong_token_argument_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="token must be an AuthenticationOneTimeToken"):
        require_usable_authentication_token(
            token=cast(Any, object()),
            now=NOW_WITHIN_VALIDITY,
        )


def test_wrong_now_argument_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="now must be a datetime"):
        require_usable_authentication_token(
            token=_build_token(),
            now=cast(Any, "2026-07-11T12:15:00Z"),
        )


def test_naive_now_raises_value_error() -> None:
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        require_usable_authentication_token(
            token=_build_token(),
            now=datetime(2026, 7, 11, 12, 15, 0),
        )


def test_policy_does_not_mutate_allowed_token() -> None:
    token = _build_token()
    before = (
        token.id,
        token.user_id,
        token.purpose,
        token.token_hash,
        token.created_at,
        token.expires_at,
        token.consumed_at,
        token.revoked_at,
    )

    require_usable_authentication_token(token=token, now=NOW_WITHIN_VALIDITY)

    after = (
        token.id,
        token.user_id,
        token.purpose,
        token.token_hash,
        token.created_at,
        token.expires_at,
        token.consumed_at,
        token.revoked_at,
    )
    assert after == before


def test_policy_does_not_mutate_denied_token() -> None:
    token = _build_token(consumed_at=CONSUMED_AT)
    before = (
        token.id,
        token.user_id,
        token.purpose,
        token.token_hash,
        token.created_at,
        token.expires_at,
        token.consumed_at,
        token.revoked_at,
    )

    with pytest.raises(AuthenticationTokenUnavailableError):
        require_usable_authentication_token(token=token, now=NOW_WITHIN_VALIDITY)

    after = (
        token.id,
        token.user_id,
        token.purpose,
        token.token_hash,
        token.created_at,
        token.expires_at,
        token.consumed_at,
        token.revoked_at,
    )
    assert after == before


def test_authentication_token_policy_symbols_can_be_imported_from_closeros_domain() -> None:
    assert AuthenticationTokenUnavailableError.__name__ == "AuthenticationTokenUnavailableError"
    assert require_usable_authentication_token.__name__ == "require_usable_authentication_token"
