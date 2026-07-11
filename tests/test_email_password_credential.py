"""Tests for CLS-011.2g email/password credential domain entity."""

# mypy: disable-error-code=import-untyped

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.domain import (
    AuthenticationEmail,
    EmailPasswordCredential,
    PasswordHash,
)

CREDENTIAL_ID = UUID("00000000-0000-0000-0000-000000000300")
USER_ID = UUID("00000000-0000-0000-0000-000000000010")
EMAIL = AuthenticationEmail(value="user@example.com")
PASSWORD_HASH = PasswordHash(
    encoded="$argon2id$v=19$m=19456,t=2,p=1$c2FsdHNhbHQ$ZGlnaWVzdGRpZ2VzdGRpZ2VzdA"
)
CREATED_AT = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
EMAIL_VERIFIED_AT = datetime(2026, 7, 11, 12, 30, 0, tzinfo=UTC)


def _build_credential(**overrides: object) -> EmailPasswordCredential:
    values = {
        "id": CREDENTIAL_ID,
        "user_id": USER_ID,
        "email": EMAIL,
        "password_hash": PASSWORD_HASH,
        "created_at": CREATED_AT,
        "email_verified_at": None,
    }
    values.update(overrides)
    return EmailPasswordCredential(**cast(Any, values))


def test_valid_unverified_credential_with_email_verified_at_none_is_accepted() -> None:
    credential = _build_credential(email_verified_at=None)

    assert credential.email_verified_at is None


def test_valid_verified_credential_is_accepted() -> None:
    credential = _build_credential(email_verified_at=EMAIL_VERIFIED_AT)

    assert credential.email_verified_at == EMAIL_VERIFIED_AT


def test_supplied_id_and_user_id_are_stored_unchanged() -> None:
    credential = _build_credential()

    assert credential.id is CREDENTIAL_ID
    assert credential.user_id is USER_ID


def test_supplied_authentication_email_is_stored_unchanged() -> None:
    credential = _build_credential()

    assert credential.email is EMAIL


def test_supplied_password_hash_is_stored_unchanged() -> None:
    credential = _build_credential()

    assert credential.password_hash is PASSWORD_HASH


def test_email_verified_at_equal_to_created_at_is_accepted() -> None:
    credential = _build_credential(email_verified_at=CREATED_AT)

    assert credential.email_verified_at == CREATED_AT


def test_email_and_password_hash_are_excluded_from_repr() -> None:
    credential_repr = repr(_build_credential())

    assert "email=" not in credential_repr
    assert "password_hash=" not in credential_repr


def test_normalized_email_text_is_not_exposed_in_repr() -> None:
    credential_repr = repr(_build_credential())

    assert EMAIL.value not in credential_repr
    assert "user@example.com" not in credential_repr


def test_argon2id_phc_text_is_not_exposed_in_repr() -> None:
    credential_repr = repr(_build_credential())

    assert PASSWORD_HASH.encoded not in credential_repr
    assert "$argon2id$" not in credential_repr


def test_non_uuid_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="id must be a UUID"):
        _build_credential(id=cast(Any, "not-a-uuid"))


def test_non_uuid_user_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="user_id must be a UUID"):
        _build_credential(user_id=cast(Any, "not-a-uuid"))


def test_plain_string_email_raises_type_error() -> None:
    with pytest.raises(TypeError, match="email must be an AuthenticationEmail"):
        _build_credential(email=cast(Any, "user@example.com"))


def test_plain_string_password_hash_raises_type_error() -> None:
    with pytest.raises(TypeError, match="password_hash must be a PasswordHash"):
        _build_credential(password_hash=cast(Any, PASSWORD_HASH.encoded))


def test_non_datetime_created_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="created_at must be a datetime"):
        _build_credential(created_at=cast(Any, "2026-07-11T12:00:00Z"))


def test_non_datetime_email_verified_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="email_verified_at must be a datetime"):
        _build_credential(email_verified_at=cast(Any, "2026-07-11T12:30:00Z"))


def test_naive_created_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        _build_credential(created_at=datetime(2026, 7, 11, 12, 0, 0))


def test_naive_email_verified_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="email_verified_at must be timezone-aware"):
        _build_credential(email_verified_at=datetime(2026, 7, 11, 12, 30, 0))


def test_email_verified_at_before_created_at_raises_value_error() -> None:
    with pytest.raises(
        ValueError,
        match="email_verified_at must be greater than or equal to created_at",
    ):
        _build_credential(
            email_verified_at=CREATED_AT - timedelta(minutes=1),
        )


def test_email_password_credential_can_be_imported_from_closeros_domain() -> None:
    assert EmailPasswordCredential.__name__ == "EmailPasswordCredential"
