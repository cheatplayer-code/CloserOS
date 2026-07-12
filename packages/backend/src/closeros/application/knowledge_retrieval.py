"""Tenant-scoped lexical knowledge retrieval with deterministic ranking."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.knowledge_audit import knowledge_retrieval_completed_event
from closeros.application.knowledge_search_key import KnowledgeSearchKeyProvider
from closeros.application.knowledge_term_index import build_query_term_digests
from closeros.domain.audit import AuditActorType
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    EncryptedContentKind,
)
from closeros.domain.knowledge import KnowledgeRetrievalResult

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalRequest:
    tenant_id: UUID
    query_text: str
    analysis_target_id: UUID
    occurred_at: datetime
    audit_context: AuditContext
    actor_type: AuditActorType
    actor_id: UUID | None
    limit: int = 8


class KnowledgeRetrievalService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        key_provider: KnowledgeSearchKeyProvider,
        content_encryption: ContentEncryptionService,
        uuid_factory: _UuidFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._key_provider = key_provider
        self._content_encryption = content_encryption
        self._uuid_factory = uuid_factory

    async def retrieve(
        self,
        request: KnowledgeRetrievalRequest,
    ) -> tuple[KnowledgeRetrievalResult, ...]:
        if type(request.query_text) is not str or not request.query_text.strip():
            return ()
        if request.limit < 1:
            raise ValueError("limit must be positive")

        term_digests = build_query_term_digests(
            tenant_id=request.tenant_id,
            query_text=request.query_text,
            key_provider=self._key_provider,
        )
        if not term_digests:
            return ()

        uow = self._uow_factory()
        async with uow:
            matches = await uow.knowledge_chunk_terms.search_ranked(
                tenant_id=request.tenant_id,
                term_digests=term_digests,
                limit=request.limit,
            )

        results: list[KnowledgeRetrievalResult] = []
        for match in matches:
            decrypted = await self._content_encryption.load_and_decrypt(
                tenant_id=request.tenant_id,
                content_id=match.content_id,
                purpose=ContentAccessPurpose.KNOWLEDGE_RETRIEVAL,
                occurred_at=request.occurred_at,
                audit_context=request.audit_context,
                actor_type=request.actor_type,
                actor_id=request.actor_id,
                audit_event_id=self._uuid_factory(),
            )
            if decrypted.kind is not EncryptedContentKind.KNOWLEDGE_CHUNK:
                continue
            if decrypted.encoding is not ContentEncoding.UTF8:
                continue
            results.append(
                KnowledgeRetrievalResult(
                    chunk_id=match.chunk_id,
                    source_code=match.source_code,
                    version_number=match.version_number,
                    document_kind=match.document_kind,
                    match_weight=match.match_weight,
                    decrypted_text=decrypted.as_utf8_text(),
                )
            )

        if results:
            audit_uow = self._uow_factory()
            async with audit_uow:
                await append_required_audit_event(
                    audit_uow.audit_events,
                    knowledge_retrieval_completed_event(
                        tenant_id=request.tenant_id,
                        analysis_target_id=request.analysis_target_id,
                        purpose_code=ContentAccessPurpose.KNOWLEDGE_RETRIEVAL.value,
                        chunk_count=len(results),
                        occurred_at=request.occurred_at,
                        audit_context=request.audit_context,
                        actor_type=request.actor_type,
                        actor_id=request.actor_id,
                        event_id=self._uuid_factory(),
                    ),
                )
                await audit_uow.commit()

        return tuple(results)
