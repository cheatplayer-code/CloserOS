"""Tests for CLS-011.2i verified-email authentication policy guard."""

# mypy: disable-error-code=import-untyped

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.domain import (
    AuthenticationEmail,
    EmailPasswordCredential,
    EmailVerificationRequiredError,
    PasswordHash,
    require_verified_email,
)

CREDENTIAL_ID = UUID("00000000-0000-0000-0000-000000000300")
USER_ID = UUID("00000000-0000-0000-0000-000000000010")
EMAIL = AuthenticationEmail(value="user@example.com")
PASSWORD_HASH = PasswordHash(
    encoded="$argon2id$v=19$m=19456,t=2,p=1$c2FsdHNhbHQ$ZGlnaWVzdGRpZ2VzdGRpZ2VzdA"
)
CREATED_AT = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
EMAIL_VERIFIED_AT = datetime(2026, 7, 11, 12, 30, 0, tzinfo=UTC)
DENIED_MESSAGE = "email verification required"


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


def test_verified_credential_is_allowed() -> None:
    credential = _build_credential(email_verified_at=EMAIL_VERIFIED_AT)

    require_verified_email(credential=credential)


def test_allowed_call_returns_none() -> None:
    credential = _build_credential(email_verified_at=EMAIL_VERIFIED_AT)
    require_verified_email_any: Any = require_verified_email

    assert require_verified_email_any(credential=credential) is None


def test_unverified_credential_is_denied() -> None:
    credential = _build_credential(email_verified_at=None)

    with pytest.raises(EmailVerificationRequiredError):
        require_verified_email(credential=credential)


def test_denied_case_raises_email_verification_required_error() -> None:
    credential = _build_credential(email_verified_at=None)

    with pytest.raises(EmailVerificationRequiredError):
        require_verified_email(credential=credential)


def test_denial_message_is_exactly_email_verification_required() -> None:
    credential = _build_credential(email_verified_at=None)

    with pytest.raises(
        EmailVerificationRequiredError,
        match=f"^{DENIED_MESSAGE}$",
    ) as exc_info:
        require_verified_email(credential=credential)

    assert str(exc_info.value) == DENIED_MESSAGE


def test_denial_message_and_repr_contain_no_sensitive_details() -> None:
    credential = _build_credential(email_verified_at=None)

    with pytest.raises(EmailVerificationRequiredError) as exc_info:
        require_verified_email(credential=credential)

    error_text = f"{exc_info.value}{repr(exc_info.value)}"
    assert str(CREDENTIAL_ID) not in error_text
    assert str(USER_ID) not in error_text
    assert EMAIL.value not in error_text
    assert PASSWORD_HASH.encoded not in error_text
    assert "$argon2id$" not in error_text


def test_wrong_credential_argument_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="credential must be an EmailPasswordCredential"):
        require_verified_email(credential=cast(Any, object()))


def test_policy_does_not_mutate_verified_credential() -> None:
    credential = _build_credential(email_verified_at=EMAIL_VERIFIED_AT)
    before = (
        credential.id,
        credential.user_id,
        credential.email,
        credential.password_hash,
        credential.created_at,
        credential.email_verified_at,
    )

    require_verified_email(credential=credential)

    after = (
        credential.id,
        credential.user_id,
        credential.email,
        credential.password_hash,
        credential.created_at,
        credential.email_verified_at,
    )
    assert after == before


def test_policy_does_not_mutate_unverified_credential() -> None:
    credential = _build_credential(email_verified_at=None)
    before = (
        credential.id,
        credential.user_id,
        credential.email,
        credential.password_hash,
        credential.created_at,
        credential.email_verified_at,
    )

    with pytest.raises(EmailVerificationRequiredError):
        require_verified_email(credential=credential)

    after = (
        credential.id,
        credential.user_id,
        credential.email,
        credential.password_hash,
        credential.created_at,
        credential.email_verified_at,
    )
    assert after == before


def test_email_verification_symbols_can_be_imported_from_closeros_domain() -> None:
    assert EmailVerificationRequiredError.__name__ == "EmailVerificationRequiredError"
    assert require_verified_email.__name__ == "require_verified_email"
