"""SQLAlchemy async unit of work composing platform, canonical, and HI persistence."""

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
from closeros.infrastructure.csv_import_repositories import (
    SqlAlchemyCsvImportBatchRepository,
    SqlAlchemyCsvImportRowErrorRepository,
)
from closeros.infrastructure.encrypted_content_repositories import (
    SqlAlchemyEncryptedContentRepository,
)
from closeros.infrastructure.outbox_repositories import (
    SqlAlchemyOutboxJobAttemptRepository,
    SqlAlchemyOutboxJobRepository,
)
from closeros.infrastructure.tenant_repositories import (
    SqlAlchemyInvitationRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyTenantRepository,
)


class SqlAlchemyIntegratedUnitOfWork:
    users: SqlAlchemyUserRepository
    credentials: SqlAlchemyCredentialRepository
    sessions: SqlAlchemySessionRepository
    one_time_tokens: SqlAlchemyOneTimeTokenRepository
    tenants: SqlAlchemyTenantRepository
    memberships: SqlAlchemyMembershipRepository
    invitations: SqlAlchemyInvitationRepository
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
    encrypted_contents: SqlAlchemyEncryptedContentRepository
    outbox_jobs: SqlAlchemyOutboxJobRepository
    outbox_job_attempts: SqlAlchemyOutboxJobAttemptRepository
    audit_events: SqlAlchemyAuditEventRepository
    csv_import_batches: SqlAlchemyCsvImportBatchRepository
    csv_import_row_errors: SqlAlchemyCsvImportRowErrorRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SqlAlchemyIntegratedUnitOfWork:
        session = self._session_factory()
        self._session = session
        self.users = SqlAlchemyUserRepository(session)
        self.credentials = SqlAlchemyCredentialRepository(session)
        self.sessions = SqlAlchemySessionRepository(session)
        self.one_time_tokens = SqlAlchemyOneTimeTokenRepository(session)
        self.tenants = SqlAlchemyTenantRepository(session)
        self.memberships = SqlAlchemyMembershipRepository(session)
        self.invitations = SqlAlchemyInvitationRepository(session)
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
        self.encrypted_contents = SqlAlchemyEncryptedContentRepository(session)
        self.outbox_jobs = SqlAlchemyOutboxJobRepository(session)
        self.outbox_job_attempts = SqlAlchemyOutboxJobAttemptRepository(session)
        self.audit_events = SqlAlchemyAuditEventRepository(session)
        self.csv_import_batches = SqlAlchemyCsvImportBatchRepository(session)
        self.csv_import_row_errors = SqlAlchemyCsvImportRowErrorRepository(session)
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
