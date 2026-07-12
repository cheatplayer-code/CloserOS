"""SQLAlchemy async unit of work composing authentication and tenant persistence."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from closeros.infrastructure.audit_repositories import SqlAlchemyAuditEventRepository
from closeros.infrastructure.authentication_repositories import (
    SqlAlchemyCredentialRepository,
    SqlAlchemyOneTimeTokenRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)
from closeros.infrastructure.authentication_unit_of_work import UnitOfWorkStateError
from closeros.infrastructure.tenant_repositories import (
    SqlAlchemyInvitationRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyTenantRepository,
)


class SqlAlchemyPlatformUnitOfWork:
    users: SqlAlchemyUserRepository
    credentials: SqlAlchemyCredentialRepository
    sessions: SqlAlchemySessionRepository
    one_time_tokens: SqlAlchemyOneTimeTokenRepository
    tenants: SqlAlchemyTenantRepository
    memberships: SqlAlchemyMembershipRepository
    invitations: SqlAlchemyInvitationRepository
    audit_events: SqlAlchemyAuditEventRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SqlAlchemyPlatformUnitOfWork:
        session = self._session_factory()
        self._session = session
        self.users = SqlAlchemyUserRepository(session)
        self.credentials = SqlAlchemyCredentialRepository(session)
        self.sessions = SqlAlchemySessionRepository(session)
        self.one_time_tokens = SqlAlchemyOneTimeTokenRepository(session)
        self.tenants = SqlAlchemyTenantRepository(session)
        self.memberships = SqlAlchemyMembershipRepository(session)
        self.invitations = SqlAlchemyInvitationRepository(session)
        self.audit_events = SqlAlchemyAuditEventRepository(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._session
        if session is None:
            return
        try:
            if exc is not None:
                await session.rollback()
        finally:
            await session.close()
            self._session = None

    async def commit(self) -> None:
        if self._session is None:
            raise UnitOfWorkStateError("unit of work is not active")
        await self._session.commit()

    async def rollback(self) -> None:
        if self._session is None:
            raise UnitOfWorkStateError("unit of work is not active")
        await self._session.rollback()
