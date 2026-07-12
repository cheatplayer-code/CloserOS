"""Application persistence ports for conversation analysis runs and findings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError


class AnalysisPersistenceError(PersistenceError):
    """Base class for safe analysis persistence failures."""


class ConversationAnalysisRunNotFoundError(AnalysisPersistenceError):
    """Raised when analysis run does not exist."""


class DuplicateConversationAnalysisRunError(AnalysisPersistenceError):
    """Raised when analysis run uniqueness is violated."""


@dataclass(frozen=True, slots=True)
class ConversationAnalysisRunRecord:
    id: UUID
    tenant_id: UUID
    conversation_thread_id: UUID
    policy_id: UUID
    purpose: str
    status: str
    prompt_version: str
    rubric_version: str
    input_digest: bytes
    knowledge_context_digest: bytes
    output_digest: bytes | None
    model_provider: str
    input_token_count: int
    output_token_count: int
    cost_minor_units: int
    requested_at: datetime
    completed_at: datetime | None
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class ConversationFindingRecord:
    id: UUID
    tenant_id: UUID
    analysis_run_id: UUID
    finding_code: str
    severity: str
    status: str
    confidence_basis_points: int
    revenue_at_risk_basis_points: int | None
    created_at: datetime
    reviewed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ConversationFindingEvidenceRecord:
    id: UUID
    tenant_id: UUID
    finding_id: UUID
    conversation_thread_id: UUID
    message_id: UUID
    excerpt_content_id: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationFindingKnowledgeCitationRecord:
    id: UUID
    tenant_id: UUID
    finding_id: UUID
    document_id: UUID
    document_version_id: UUID
    chunk_id: UUID
    retrieval_rank: int
    relevance_basis_points: int
    created_at: datetime


class ConversationAnalysisRunRepository(Protocol):
    async def add(self, *, record: ConversationAnalysisRunRecord) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
    ) -> ConversationAnalysisRunRecord | None: ...

    async def get_by_id_for_update(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
    ) -> ConversationAnalysisRunRecord | None: ...

    async def update(self, *, record: ConversationAnalysisRunRecord) -> None: ...

    async def list_by_tenant(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID | None = None,
        limit: int = 50,
    ) -> tuple[ConversationAnalysisRunRecord, ...]: ...


class ConversationFindingRepository(Protocol):
    async def replace_for_run(
        self,
        *,
        tenant_id: UUID,
        analysis_run_id: UUID,
        findings: tuple[ConversationFindingRecord, ...],
    ) -> None: ...

    async def list_by_run(
        self,
        *,
        tenant_id: UUID,
        analysis_run_id: UUID,
    ) -> tuple[ConversationFindingRecord, ...]: ...


class ConversationFindingEvidenceRepository(Protocol):
    async def replace_for_findings(
        self,
        *,
        tenant_id: UUID,
        finding_ids: tuple[UUID, ...],
        evidence: tuple[ConversationFindingEvidenceRecord, ...],
    ) -> None: ...

    async def list_by_finding_ids(
        self,
        *,
        tenant_id: UUID,
        finding_ids: tuple[UUID, ...],
    ) -> tuple[ConversationFindingEvidenceRecord, ...]: ...


class ConversationFindingKnowledgeCitationRepository(Protocol):
    async def replace_for_findings(
        self,
        *,
        tenant_id: UUID,
        finding_ids: tuple[UUID, ...],
        citations: tuple[ConversationFindingKnowledgeCitationRecord, ...],
    ) -> None: ...

    async def list_by_finding_ids(
        self,
        *,
        tenant_id: UUID,
        finding_ids: tuple[UUID, ...],
    ) -> tuple[ConversationFindingKnowledgeCitationRecord, ...]: ...
