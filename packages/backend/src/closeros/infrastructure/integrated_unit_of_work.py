"""SQLAlchemy async unit of work composing platform, canonical, and HI persistence."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from closeros.infrastructure.ai_policy_repositories import (
    SqlAlchemyAiUsageDailyRepository,
    SqlAlchemyTenantAiPolicyRepository,
)
from closeros.infrastructure.analysis_repositories import (
    SqlAlchemyConversationAnalysisRunRepository,
    SqlAlchemyConversationFindingEvidenceRepository,
    SqlAlchemyConversationFindingKnowledgeCitationRepository,
    SqlAlchemyConversationFindingRepository,
)
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
from closeros.infrastructure.content_sanitization_repositories import (
    SqlAlchemyContentSanitizationRepository,
)
from closeros.infrastructure.csv_import_repositories import (
    SqlAlchemyCsvImportBatchRepository,
    SqlAlchemyCsvImportRowErrorRepository,
)
from closeros.infrastructure.encrypted_content_repositories import (
    SqlAlchemyEncryptedContentRepository,
)
from closeros.infrastructure.follow_up_task_repositories import SqlAlchemyFollowUpTaskRepository
from closeros.infrastructure.knowledge_repositories import (
    SqlAlchemyKnowledgeChunkRepository,
    SqlAlchemyKnowledgeChunkTermRepository,
    SqlAlchemyKnowledgeDocumentRepository,
    SqlAlchemyKnowledgeDocumentVersionRepository,
)
from closeros.infrastructure.metrics_repositories import SqlAlchemyMetricSnapshotRepository
from closeros.infrastructure.outbound_repositories import (
    SqlAlchemyOutboundDeliveryAttemptRepository,
    SqlAlchemyOutboundMessageRepository,
)
from closeros.infrastructure.outbox_repositories import (
    SqlAlchemyOutboxJobAttemptRepository,
    SqlAlchemyOutboxJobRepository,
)
from closeros.infrastructure.provider_media_repositories import (
    SqlAlchemyProviderMediaReferenceRepository,
)
from closeros.infrastructure.provider_template_repositories import (
    SqlAlchemyProviderMessageTemplateRepository,
)
from closeros.infrastructure.tenant_repositories import (
    SqlAlchemyInvitationRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyTenantRepository,
)
from closeros.infrastructure.whatsapp_repositories import (
    SqlAlchemyWhatsAppCloudConnectionRepository,
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
    content_sanitizations: SqlAlchemyContentSanitizationRepository
    metric_snapshots: SqlAlchemyMetricSnapshotRepository
    knowledge_documents: SqlAlchemyKnowledgeDocumentRepository
    knowledge_document_versions: SqlAlchemyKnowledgeDocumentVersionRepository
    knowledge_chunks: SqlAlchemyKnowledgeChunkRepository
    knowledge_chunk_terms: SqlAlchemyKnowledgeChunkTermRepository
    tenant_ai_policies: SqlAlchemyTenantAiPolicyRepository
    ai_usage_daily: SqlAlchemyAiUsageDailyRepository
    conversation_analysis_runs: SqlAlchemyConversationAnalysisRunRepository
    conversation_findings: SqlAlchemyConversationFindingRepository
    conversation_finding_evidence: SqlAlchemyConversationFindingEvidenceRepository
    conversation_finding_knowledge_citations: (
        SqlAlchemyConversationFindingKnowledgeCitationRepository
    )
    follow_up_tasks: SqlAlchemyFollowUpTaskRepository
    whatsapp_cloud_connections: SqlAlchemyWhatsAppCloudConnectionRepository
    provider_message_templates: SqlAlchemyProviderMessageTemplateRepository
    provider_media_references: SqlAlchemyProviderMediaReferenceRepository
    outbound_messages: SqlAlchemyOutboundMessageRepository
    outbound_delivery_attempts: SqlAlchemyOutboundDeliveryAttemptRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise UnitOfWorkStateError("unit of work is not active")
        return self._session

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
        self.content_sanitizations = SqlAlchemyContentSanitizationRepository(session)
        self.metric_snapshots = SqlAlchemyMetricSnapshotRepository(session)
        self.knowledge_documents = SqlAlchemyKnowledgeDocumentRepository(session)
        self.knowledge_document_versions = SqlAlchemyKnowledgeDocumentVersionRepository(session)
        self.knowledge_chunks = SqlAlchemyKnowledgeChunkRepository(session)
        self.knowledge_chunk_terms = SqlAlchemyKnowledgeChunkTermRepository(session)
        self.tenant_ai_policies = SqlAlchemyTenantAiPolicyRepository(session)
        self.ai_usage_daily = SqlAlchemyAiUsageDailyRepository(session)
        self.conversation_analysis_runs = SqlAlchemyConversationAnalysisRunRepository(session)
        self.conversation_findings = SqlAlchemyConversationFindingRepository(session)
        self.conversation_finding_evidence = SqlAlchemyConversationFindingEvidenceRepository(
            session
        )
        self.conversation_finding_knowledge_citations = (
            SqlAlchemyConversationFindingKnowledgeCitationRepository(session)
        )
        self.follow_up_tasks = SqlAlchemyFollowUpTaskRepository(session)
        self.whatsapp_cloud_connections = SqlAlchemyWhatsAppCloudConnectionRepository(session)
        self.provider_message_templates = SqlAlchemyProviderMessageTemplateRepository(session)
        self.provider_media_references = SqlAlchemyProviderMediaReferenceRepository(session)
        self.outbound_messages = SqlAlchemyOutboundMessageRepository(session)
        self.outbound_delivery_attempts = SqlAlchemyOutboundDeliveryAttemptRepository(session)
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
