"""Application-layer persistence ports for the authentication subsystem.

These protocols define the repository and unit-of-work contracts that the
authentication workflows depend on. The application layer must never import
SQLAlchemy, Alembic, psycopg, or any other persistence technology; concrete
implementations live in the infrastructure layer.

Repositories never commit. The unit of work owns commit and rollback.
"""

from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from closeros.domain.authentication import (
    AuthenticationEmail,
    AuthenticationTokenHash,
    AuthenticationTokenPurpose,
    PasswordHash,
)
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.authentication_token import AuthenticationOneTimeToken
from closeros.domain.email_password_credential import EmailPasswordCredential
from closeros.domain.identity import UserStatus
from closeros.domain.user import User


class AuthenticationPersistenceError(Exception):
    """Base class for safe authentication persistence failures.

    Instances must never carry raw passwords, raw tokens, hashes, email
    addresses, or SQL fragments in their messages.
    """


class AuthenticationRecordNotFoundError(AuthenticationPersistenceError):
    """Raised when an update targets a record that does not exist."""


class DuplicateCredentialEmailError(AuthenticationPersistenceError):
    """Raised when a credential email already exists."""


class DuplicateUserCredentialError(AuthenticationPersistenceError):
    """Raised when a user already has a credential."""


class DuplicateSessionTokenError(AuthenticationPersistenceError):
    """Raised when a session token hash already exists."""


class DuplicateOneTimeTokenError(AuthenticationPersistenceError):
    """Raised when a one-time-token hash already exists."""


class AuthenticationReferenceError(AuthenticationPersistenceError):
    """Raised when a referenced user does not exist."""


class UserRepository(Protocol):
    async def add(self, user: User) -> None: ...

    async def get_by_id(self, user_id: UUID) -> User | None: ...

    async def update_status(
        self,
        *,
        user_id: UUID,
        status: UserStatus,
    ) -> None: ...


class CredentialRepository(Protocol):
    async def add(self, credential: EmailPasswordCredential) -> None: ...

    async def get_by_id(
        self,
        credential_id: UUID,
    ) -> EmailPasswordCredential | None: ...

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> EmailPasswordCredential | None: ...

    async def get_by_email(
        self,
        email: AuthenticationEmail,
    ) -> EmailPasswordCredential | None: ...

    async def get_by_email_for_update(
        self,
        email: AuthenticationEmail,
    ) -> EmailPasswordCredential | None: ...

    async def set_email_verified_at(
        self,
        *,
        credential_id: UUID,
        verified_at: datetime,
    ) -> None: ...

    async def replace_password_hash(
        self,
        *,
        credential_id: UUID,
        password_hash: PasswordHash,
    ) -> None: ...


class SessionRepository(Protocol):
    async def add(self, session: AuthenticationSession) -> None: ...

    async def get_by_id(
        self,
        session_id: UUID,
    ) -> AuthenticationSession | None: ...

    async def get_by_token_hash(
        self,
        token_hash: AuthenticationTokenHash,
    ) -> AuthenticationSession | None: ...

    async def get_by_token_hash_for_update(
        self,
        token_hash: AuthenticationTokenHash,
    ) -> AuthenticationSession | None: ...

    async def list_active_for_user(
        self,
        *,
        user_id: UUID,
        now: datetime,
    ) -> tuple[AuthenticationSession, ...]: ...

    async def update_last_seen(
        self,
        *,
        session_id: UUID,
        last_seen_at: datetime,
    ) -> None: ...

    async def revoke(
        self,
        *,
        session_id: UUID,
        revoked_at: datetime,
    ) -> None: ...

    async def revoke_all_for_user(
        self,
        *,
        user_id: UUID,
        revoked_at: datetime,
    ) -> int: ...


class OneTimeTokenRepository(Protocol):
    async def add(self, token: AuthenticationOneTimeToken) -> None: ...

    async def get_by_token_hash(
        self,
        token_hash: AuthenticationTokenHash,
    ) -> AuthenticationOneTimeToken | None: ...

    async def get_by_token_hash_for_update(
        self,
        token_hash: AuthenticationTokenHash,
    ) -> AuthenticationOneTimeToken | None: ...

    async def consume(
        self,
        *,
        token_id: UUID,
        consumed_at: datetime,
    ) -> None: ...

    async def consume_if_usable(
        self,
        *,
        token_id: UUID,
        consumed_at: datetime,
        now: datetime,
    ) -> bool: ...

    async def revoke(
        self,
        *,
        token_id: UUID,
        revoked_at: datetime,
    ) -> None: ...

    async def revoke_active_for_user_and_purpose(
        self,
        *,
        user_id: UUID,
        purpose: AuthenticationTokenPurpose,
        revoked_at: datetime,
    ) -> int: ...


class AuthenticationUnitOfWork(Protocol):
    users: UserRepository
    credentials: CredentialRepository
    sessions: SessionRepository
    one_time_tokens: OneTimeTokenRepository

    async def __aenter__(self) -> AuthenticationUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
