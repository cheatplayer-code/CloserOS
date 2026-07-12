"""Explicit mapping between authentication ORM rows and domain objects.

ORM rows never leave the infrastructure layer. These pure functions translate
in both directions so repositories can accept and return framework-independent
domain entities only.
"""

from __future__ import annotations

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
from closeros.infrastructure.authentication_orm import (
    CredentialRow,
    OneTimeTokenRow,
    SessionRow,
    UserRow,
)


def user_to_row(user: User) -> UserRow:
    return UserRow(id=user.id, status=user.status.value)


def user_to_domain(row: UserRow) -> User:
    return User(id=row.id, status=UserStatus(row.status))


def credential_to_row(credential: EmailPasswordCredential) -> CredentialRow:
    return CredentialRow(
        id=credential.id,
        user_id=credential.user_id,
        email=credential.email.value,
        password_hash=credential.password_hash.encoded,
        created_at=credential.created_at,
        email_verified_at=credential.email_verified_at,
    )


def credential_to_domain(row: CredentialRow) -> EmailPasswordCredential:
    return EmailPasswordCredential(
        id=row.id,
        user_id=row.user_id,
        email=AuthenticationEmail(row.email),
        password_hash=PasswordHash(row.password_hash),
        created_at=row.created_at,
        email_verified_at=row.email_verified_at,
    )


def session_to_row(session: AuthenticationSession) -> SessionRow:
    return SessionRow(
        id=session.id,
        user_id=session.user_id,
        token_hash=session.token_hash.digest,
        stage=session.stage.value,
        assurance_level=session.assurance_level.value,
        mfa_completed=session.mfa_completed,
        created_at=session.created_at,
        last_seen_at=session.last_seen_at,
        expires_at=session.expires_at,
        revoked_at=session.revoked_at,
    )


def session_to_domain(row: SessionRow) -> AuthenticationSession:
    return AuthenticationSession(
        id=row.id,
        user_id=row.user_id,
        token_hash=AuthenticationTokenHash(digest=bytes(row.token_hash)),
        stage=AuthenticationSessionStage(row.stage),
        assurance_level=AuthenticationAssuranceLevel(row.assurance_level),
        mfa_completed=row.mfa_completed,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
    )


def one_time_token_to_row(token: AuthenticationOneTimeToken) -> OneTimeTokenRow:
    return OneTimeTokenRow(
        id=token.id,
        user_id=token.user_id,
        purpose=token.purpose.value,
        token_hash=token.token_hash.digest,
        created_at=token.created_at,
        expires_at=token.expires_at,
        consumed_at=token.consumed_at,
        revoked_at=token.revoked_at,
    )


def one_time_token_to_domain(row: OneTimeTokenRow) -> AuthenticationOneTimeToken:
    return AuthenticationOneTimeToken(
        id=row.id,
        user_id=row.user_id,
        purpose=AuthenticationTokenPurpose(row.purpose),
        token_hash=AuthenticationTokenHash(digest=bytes(row.token_hash)),
        created_at=row.created_at,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
        revoked_at=row.revoked_at,
    )
