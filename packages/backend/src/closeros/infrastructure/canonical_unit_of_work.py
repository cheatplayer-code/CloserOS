"""SQLAlchemy async unit of work for canonical conversation persistence."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from closeros.infrastructure.audit_repositories import SqlAlchemyAuditEventRepository
from closeros.infrastructure.authentication_unit_of_work import UnitOfWorkStateError
from closeros.infrastructure.canonical_repositories import (
    SqlAlchemyChannelConnectionRepository,
    SqlAlchemyConversationThreadRepository,
    SqlAlchemyCRMOutcomeRepository,
    SqlAlchemyLeadRepository,
    SqlAlchemyManagerAssignmentRepository,
    SqlAlchemyMessageDeletionEventRepository,
    SqlAlchemyMessageDeliveryStatusEventRepository,
    SqlAlchemyMessageEditEventRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemySalesCaseRepository,
    SqlAlchemyWebhookEventRepository,
)


class SqlAlchemyCanonicalUnitOfWork:
    channel_connections: SqlAlchemyChannelConnectionRepository
    leads: SqlAlchemyLeadRepository
    sales_cases: SqlAlchemySalesCaseRepository
    conversation_threads: SqlAlchemyConversationThreadRepository
    messages: SqlAlchemyMessageRepository
    message_edit_events: SqlAlchemyMessageEditEventRepository
    message_deletion_events: SqlAlchemyMessageDeletionEventRepository
    message_delivery_status_events: SqlAlchemyMessageDeliveryStatusEventRepository
    manager_assignments: SqlAlchemyManagerAssignmentRepository
    crm_outcomes: SqlAlchemyCRMOutcomeRepository
    webhook_events: SqlAlchemyWebhookEventRepository
    audit_events: SqlAlchemyAuditEventRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SqlAlchemyCanonicalUnitOfWork:
        session = self._session_factory()
        self._session = session
        self.channel_connections = SqlAlchemyChannelConnectionRepository(session)
        self.leads = SqlAlchemyLeadRepository(session)
        self.sales_cases = SqlAlchemySalesCaseRepository(session)
        self.conversation_threads = SqlAlchemyConversationThreadRepository(session)
        self.messages = SqlAlchemyMessageRepository(session)
        self.message_edit_events = SqlAlchemyMessageEditEventRepository(session)
        self.message_deletion_events = SqlAlchemyMessageDeletionEventRepository(session)
        self.message_delivery_status_events = SqlAlchemyMessageDeliveryStatusEventRepository(
            session
        )
        self.manager_assignments = SqlAlchemyManagerAssignmentRepository(session)
        self.crm_outcomes = SqlAlchemyCRMOutcomeRepository(session)
        self.webhook_events = SqlAlchemyWebhookEventRepository(session)
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
