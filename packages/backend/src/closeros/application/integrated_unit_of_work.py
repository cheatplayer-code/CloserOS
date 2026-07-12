"""Application-layer unit-of-work port composing platform, canonical, and HI persistence."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

from closeros.application.ai_policy_persistence import (
    AiUsageDailyRepository,
    TenantAiPolicyRepository,
)
from closeros.application.analysis_persistence import (
    ConversationAnalysisRunRepository,
    ConversationFindingEvidenceRepository,
    ConversationFindingKnowledgeCitationRepository,
    ConversationFindingRepository,
)
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
from closeros.application.content_sanitization_persistence import ContentSanitizationRepository
from closeros.application.csv_import_persistence import (
    CsvImportBatchRepository,
    CsvImportRowErrorRepository,
)
from closeros.application.encrypted_content_persistence import EncryptedContentRepository
from closeros.application.follow_up_task_persistence import FollowUpTaskRepository
from closeros.application.knowledge_persistence import (
    KnowledgeChunkRepository,
    KnowledgeChunkTermRepository,
    KnowledgeDocumentRepository,
    KnowledgeDocumentVersionRepository,
)
from closeros.application.metrics_persistence import MetricSnapshotRepository
from closeros.application.outbound_persistence import (
    OutboundDeliveryAttemptRepository,
    OutboundMessageRepository,
)
from closeros.application.outbox_persistence import (
    OutboxJobAttemptRepository,
    OutboxJobRepository,
)
from closeros.application.provider_media_persistence import ProviderMediaReferenceRepository
from closeros.application.provider_template_persistence import ProviderMessageTemplateRepository
from closeros.application.tenant_persistence import (
    InvitationRepository,
    MembershipRepository,
    TenantRepository,
)
from closeros.application.whatsapp_persistence import WhatsAppCloudConnectionRepository


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
    content_sanitizations: ContentSanitizationRepository
    metric_snapshots: MetricSnapshotRepository
    knowledge_documents: KnowledgeDocumentRepository
    knowledge_document_versions: KnowledgeDocumentVersionRepository
    knowledge_chunks: KnowledgeChunkRepository
    knowledge_chunk_terms: KnowledgeChunkTermRepository
    tenant_ai_policies: TenantAiPolicyRepository
    ai_usage_daily: AiUsageDailyRepository
    conversation_analysis_runs: ConversationAnalysisRunRepository
    conversation_findings: ConversationFindingRepository
    conversation_finding_evidence: ConversationFindingEvidenceRepository
    conversation_finding_knowledge_citations: ConversationFindingKnowledgeCitationRepository
    follow_up_tasks: FollowUpTaskRepository
    whatsapp_cloud_connections: WhatsAppCloudConnectionRepository
    provider_message_templates: ProviderMessageTemplateRepository
    provider_media_references: ProviderMediaReferenceRepository
    outbound_messages: OutboundMessageRepository
    outbound_delivery_attempts: OutboundDeliveryAttemptRepository

    async def __aenter__(self) -> IntegratedUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
