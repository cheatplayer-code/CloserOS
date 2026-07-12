"""PostgreSQL repository implementations for the authentication subsystem.

Repositories translate expected integrity failures into safe application
exceptions that never leak SQL, hashes, emails, or credentials. They flush to
surface integrity errors early, but they never commit: the unit of work owns
commit and rollback.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.authentication_persistence import (
    AuthenticationPersistenceError,
    AuthenticationRecordNotFoundError,
    AuthenticationReferenceError,
    DuplicateCredentialEmailError,
    DuplicateOneTimeTokenError,
    DuplicateSessionTokenError,
    DuplicateUserCredentialError,
)
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
from closeros.infrastructure import authentication_mappers as mappers
from closeros.infrastructure.authentication_orm import (
    CredentialRow,
    OneTimeTokenRow,
    SessionRow,
    UserRow,
)

_CONSTRAINT_ERRORS: dict[str, type[AuthenticationPersistenceError]] = {
    "uq_authentication_credentials_email": DuplicateCredentialEmailError,
    "uq_authentication_credentials_user_id": DuplicateUserCredentialError,
    "uq_authentication_sessions_token_hash": DuplicateSessionTokenError,
    "uq_authentication_one_time_tokens_token_hash": DuplicateOneTimeTokenError,
    "fk_authentication_credentials_user_id_users": AuthenticationReferenceError,
    "fk_authentication_sessions_user_id_users": AuthenticationReferenceError,
    "fk_authentication_one_time_tokens_user_id_users": AuthenticationReferenceError,
}


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostics = getattr(error.orig, "diag", None)
    name = getattr(diagnostics, "constraint_name", None)
    return name if isinstance(name, str) else None


def _translate_integrity_error(error: IntegrityError) -> AuthenticationPersistenceError:
    name = _constraint_name(error)
    if name is not None:
        error_type = _CONSTRAINT_ERRORS.get(name)
        if error_type is not None:
            return error_type("authentication persistence constraint violated")
    return AuthenticationPersistenceError("authentication persistence integrity error")


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        self._session.add(mappers.user_to_row(user))
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error

    async def get_by_id(self, user_id: UUID) -> User | None:
        row = await self._session.get(UserRow, user_id)
        return None if row is None else mappers.user_to_domain(row)

    async def update_status(self, *, user_id: UUID, status: UserStatus) -> None:
        row = await self._session.get(UserRow, user_id)
        if row is None:
            raise AuthenticationRecordNotFoundError("user not found")
        row.status = status.value
        await self._session.flush()


class SqlAlchemyCredentialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, credential: EmailPasswordCredential) -> None:
        self._session.add(mappers.credential_to_row(credential))
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error

    async def get_by_id(self, credential_id: UUID) -> EmailPasswordCredential | None:
        row = await self._session.get(CredentialRow, credential_id)
        return None if row is None else mappers.credential_to_domain(row)

    async def get_by_user_id(self, user_id: UUID) -> EmailPasswordCredential | None:
        row = (
            await self._session.execute(
                select(CredentialRow).where(CredentialRow.user_id == user_id)
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.credential_to_domain(row)

    async def get_by_email(
        self,
        email: AuthenticationEmail,
    ) -> EmailPasswordCredential | None:
        row = (
            await self._session.execute(
                select(CredentialRow).where(CredentialRow.email == email.value)
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.credential_to_domain(row)

    async def set_email_verified_at(
        self,
        *,
        credential_id: UUID,
        verified_at: datetime,
    ) -> None:
        row = await self._session.get(CredentialRow, credential_id)
        if row is None:
            raise AuthenticationRecordNotFoundError("credential not found")
        row.email_verified_at = verified_at
        await self._session.flush()

    async def replace_password_hash(
        self,
        *,
        credential_id: UUID,
        password_hash: PasswordHash,
    ) -> None:
        row = await self._session.get(CredentialRow, credential_id)
        if row is None:
            raise AuthenticationRecordNotFoundError("credential not found")
        row.password_hash = password_hash.encoded
        await self._session.flush()


class SqlAlchemySessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: AuthenticationSession) -> None:
        self._session.add(mappers.session_to_row(session))
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error

    async def get_by_id(self, session_id: UUID) -> AuthenticationSession | None:
        row = await self._session.get(SessionRow, session_id)
        return None if row is None else mappers.session_to_domain(row)

    async def get_by_token_hash(
        self,
        token_hash: AuthenticationTokenHash,
    ) -> AuthenticationSession | None:
        row = (
            await self._session.execute(
                select(SessionRow).where(SessionRow.token_hash == token_hash.digest)
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.session_to_domain(row)

    async def list_active_for_user(
        self,
        *,
        user_id: UUID,
        now: datetime,
    ) -> tuple[AuthenticationSession, ...]:
        rows = (
            (
                await self._session.execute(
                    select(SessionRow)
                    .where(
                        SessionRow.user_id == user_id,
                        SessionRow.revoked_at.is_(None),
                        SessionRow.expires_at > now,
                    )
                    .order_by(SessionRow.created_at)
                )
            )
            .scalars()
            .all()
        )
        return tuple(mappers.session_to_domain(row) for row in rows)

    async def update_last_seen(
        self,
        *,
        session_id: UUID,
        last_seen_at: datetime,
    ) -> None:
        row = await self._session.get(SessionRow, session_id)
        if row is None:
            raise AuthenticationRecordNotFoundError("session not found")
        row.last_seen_at = last_seen_at
        await self._session.flush()

    async def revoke(self, *, session_id: UUID, revoked_at: datetime) -> None:
        row = await self._session.get(SessionRow, session_id)
        if row is None:
            raise AuthenticationRecordNotFoundError("session not found")
        if row.revoked_at is None:
            row.revoked_at = revoked_at
        await self._session.flush()

    async def revoke_all_for_user(
        self,
        *,
        user_id: UUID,
        revoked_at: datetime,
    ) -> int:
        result = await self._session.execute(
            update(SessionRow)
            .where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        rowcount = cast(Any, result).rowcount
        return 0 if rowcount is None else int(rowcount)


class SqlAlchemyOneTimeTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: AuthenticationOneTimeToken) -> None:
        self._session.add(mappers.one_time_token_to_row(token))
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error

    async def get_by_token_hash(
        self,
        token_hash: AuthenticationTokenHash,
    ) -> AuthenticationOneTimeToken | None:
        row = (
            await self._session.execute(
                select(OneTimeTokenRow).where(OneTimeTokenRow.token_hash == token_hash.digest)
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.one_time_token_to_domain(row)

    async def consume(self, *, token_id: UUID, consumed_at: datetime) -> None:
        row = await self._session.get(OneTimeTokenRow, token_id)
        if row is None:
            raise AuthenticationRecordNotFoundError("one-time token not found")
        row.consumed_at = consumed_at
        await self._session.flush()

    async def revoke(self, *, token_id: UUID, revoked_at: datetime) -> None:
        row = await self._session.get(OneTimeTokenRow, token_id)
        if row is None:
            raise AuthenticationRecordNotFoundError("one-time token not found")
        if row.revoked_at is None:
            row.revoked_at = revoked_at
        await self._session.flush()

    async def revoke_active_for_user_and_purpose(
        self,
        *,
        user_id: UUID,
        purpose: AuthenticationTokenPurpose,
        revoked_at: datetime,
    ) -> int:
        result = await self._session.execute(
            update(OneTimeTokenRow)
            .where(
                OneTimeTokenRow.user_id == user_id,
                OneTimeTokenRow.purpose == purpose.value,
                OneTimeTokenRow.revoked_at.is_(None),
                OneTimeTokenRow.consumed_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        rowcount = cast(Any, result).rowcount
        return 0 if rowcount is None else int(rowcount)
