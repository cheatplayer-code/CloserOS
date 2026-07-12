"""Application-layer unit-of-work port composing platform, canonical, and HI persistence."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

from closeros.application.audit_persistence import AuditEventAppendRepository
from closeros.application.authentication_persistence import (
    CredentialRepository,
    OneTimeTokenRepository,
    SessionRepository,
    UserRepository,
)
from closeros.application.canonical_persistence import (
    ChannelConnectionRepository,
    ConversationThreadRepository,
    CRMOutcomeRepository,
    LeadRepository,
    ManagerAssignmentRepository,
    MessageDeletionEventRepository,
    MessageDeliveryStatusEventRepository,
    MessageEditEventRepository,
    MessageRepository,
    SalesCaseRepository,
    WebhookEventRepository,
)
from closeros.application.csv_import_persistence import (
    CsvImportBatchRepository,
    CsvImportRowErrorRepository,
)
from closeros.application.encrypted_content_persistence import EncryptedContentRepository
from closeros.application.outbox_persistence import (
    OutboxJobAttemptRepository,
    OutboxJobRepository,
)
from closeros.application.tenant_persistence import (
    InvitationRepository,
    MembershipRepository,
    TenantRepository,
)


class IntegratedUnitOfWork(Protocol):
    users: UserRepository
    credentials: CredentialRepository
    sessions: SessionRepository
    one_time_tokens: OneTimeTokenRepository
    tenants: TenantRepository
    memberships: MembershipRepository
    invitations: InvitationRepository
    channel_connections: ChannelConnectionRepository
    leads: LeadRepository
    sales_cases: SalesCaseRepository
    conversation_threads: ConversationThreadRepository
    messages: MessageRepository
    message_edit_events: MessageEditEventRepository
    message_deletion_events: MessageDeletionEventRepository
    message_delivery_status_events: MessageDeliveryStatusEventRepository
    manager_assignments: ManagerAssignmentRepository
    crm_outcomes: CRMOutcomeRepository
    webhook_events: WebhookEventRepository
    encrypted_contents: EncryptedContentRepository
    outbox_jobs: OutboxJobRepository
    outbox_job_attempts: OutboxJobAttemptRepository
    audit_events: AuditEventAppendRepository
    csv_import_batches: CsvImportBatchRepository
    csv_import_row_errors: CsvImportRowErrorRepository

    async def __aenter__(self) -> IntegratedUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
