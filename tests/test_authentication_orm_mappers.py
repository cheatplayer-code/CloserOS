"""Tests for authentication ORM ↔ domain mapping."""

# mypy: disable-error-code=import-untyped

from closeros.domain.authentication import AuthenticationTokenPurpose
from closeros.domain.identity import UserStatus
from closeros.infrastructure import authentication_mappers as mappers

from tests.auth_persistence_support import (
    OTHER_TOKEN_ID,
    OTHER_USER_ID,
    SYNTHETIC_EMAIL,
    TOKEN_HASH_B,
    synthetic_credential,
    synthetic_one_time_token,
    synthetic_session,
    synthetic_user,
)


def test_user_round_trip_preserves_fields() -> None:
    user = synthetic_user()

    row = mappers.user_to_row(user)
    restored = mappers.user_to_domain(row)

    assert restored.id == user.id
    assert restored.status is UserStatus.ACTIVE


def test_credential_round_trip_preserves_normalized_email_and_hash() -> None:
    credential = synthetic_credential()

    row = mappers.credential_to_row(credential)
    restored = mappers.credential_to_domain(row)

    assert restored.id == credential.id
    assert restored.email.value == SYNTHETIC_EMAIL.value
    assert restored.password_hash.encoded == credential.password_hash.encoded
    assert restored.email_verified_at is None


def test_session_round_trip_preserves_token_hash_bytes() -> None:
    session = synthetic_session(token_hash=TOKEN_HASH_B)

    row = mappers.session_to_row(session)
    restored = mappers.session_to_domain(row)

    assert restored.token_hash.digest == TOKEN_HASH_B.digest
    assert restored.stage == session.stage
    assert restored.mfa_completed is True


def test_one_time_token_round_trip_preserves_purpose() -> None:
    token = synthetic_one_time_token(
        token_id=OTHER_TOKEN_ID,
        user_id=OTHER_USER_ID,
        purpose=AuthenticationTokenPurpose.PASSWORD_RESET,
    )

    row = mappers.one_time_token_to_row(token)
    restored = mappers.one_time_token_to_domain(row)

    assert restored.purpose is AuthenticationTokenPurpose.PASSWORD_RESET
    assert restored.consumed_at is None
    assert restored.revoked_at is None
