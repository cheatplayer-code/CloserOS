"""Synthetic fixtures for authentication persistence integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from closeros.domain.authentication import (
    AuthenticationAssuranceLevel,
    AuthenticationEmail,
    AuthenticationSessionStage,
    AuthenticationTokenHash,
    AuthenticationTokenPurpose,
    PasswordHash,
)
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.authentication_token import AuthenticationOneTimeToken
from closeros.domain.email_password_credential import EmailPasswordCredential
from closeros.domain.identity import UserStatus
from closeros.domain.user import User

USER_ID = UUID("00000000-0000-0000-0000-000000000010")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000011")
CREDENTIAL_ID = UUID("00000000-0000-0000-0000-000000000020")
SESSION_ID = UUID("00000000-0000-0000-0000-000000000100")
OTHER_SESSION_ID = UUID("00000000-0000-0000-0000-000000000101")
TOKEN_ID = UUID("00000000-0000-0000-0000-000000000200")
OTHER_TOKEN_ID = UUID("00000000-0000-0000-0000-000000000201")

NOW = datetime(2026, 7, 12, 6, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=12)

TOKEN_HASH_A = AuthenticationTokenHash(digest=bytes(range(32)))
TOKEN_HASH_B = AuthenticationTokenHash(digest=bytes(reversed(range(32))))

SYNTHETIC_EMAIL = AuthenticationEmail("persistence.test@example.test")
OTHER_EMAIL = AuthenticationEmail("other.test@example.test")

# Valid Argon2id PHC string shape for mapper round trips only; not a real hash.
SYNTHETIC_PHC = "$argon2id$v=19$m=19456,t=2,p=1$c2FsdHNhbHRzYWx0$c2FsdHNhbHRzYWx0c2FsdHNhbHRzYWx0"


def synthetic_user(*, user_id: UUID = USER_ID) -> User:
    return User(id=user_id, status=UserStatus.ACTIVE)


def synthetic_credential(
    *,
    credential_id: UUID = CREDENTIAL_ID,
    user_id: UUID = USER_ID,
    email: AuthenticationEmail = SYNTHETIC_EMAIL,
) -> EmailPasswordCredential:
    return EmailPasswordCredential(
        id=credential_id,
        user_id=user_id,
        email=email,
        password_hash=PasswordHash(SYNTHETIC_PHC),
        created_at=NOW,
        email_verified_at=None,
    )


def synthetic_session(
    *,
    session_id: UUID = SESSION_ID,
    user_id: UUID = USER_ID,
    token_hash: AuthenticationTokenHash = TOKEN_HASH_A,
) -> AuthenticationSession:
    return AuthenticationSession(
        id=session_id,
        user_id=user_id,
        token_hash=token_hash,
        stage=AuthenticationSessionStage.AUTHENTICATED,
        assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
        mfa_completed=True,
        created_at=NOW,
        last_seen_at=NOW,
        expires_at=LATER,
        revoked_at=None,
    )


def synthetic_one_time_token(
    *,
    token_id: UUID = TOKEN_ID,
    user_id: UUID = USER_ID,
    purpose: AuthenticationTokenPurpose = AuthenticationTokenPurpose.EMAIL_VERIFICATION,
    token_hash: AuthenticationTokenHash = TOKEN_HASH_A,
) -> AuthenticationOneTimeToken:
    return AuthenticationOneTimeToken(
        id=token_id,
        user_id=user_id,
        purpose=purpose,
        token_hash=token_hash,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
        consumed_at=None,
        revoked_at=None,
    )
