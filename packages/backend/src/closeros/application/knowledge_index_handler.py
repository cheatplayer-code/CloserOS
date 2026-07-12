"""Outbox handler for deterministic `knowledge.index` processing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.content_encryption_service import (
    ContentEncryptionService,
    ContentEncryptionUnavailableError,
)
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.knowledge_audit import knowledge_version_indexed_event
from closeros.application.knowledge_chunking import chunk_text_with_overlap
from closeros.application.knowledge_persistence import (
    KnowledgeChunkRecord,
    KnowledgeChunkTermRecord,
)
from closeros.application.knowledge_search_key import KnowledgeSearchKeyProvider
from closeros.application.knowledge_term_index import build_chunk_term_index
from closeros.domain.audit import AuditActorType
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    EncryptedContentKind,
)
from closeros.domain.outbox import OutboxErrorCode, OutboxJob

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]


class KnowledgeIndexHandlerError(Exception):
    def __init__(self, *, error_code: OutboxErrorCode, permanent: bool) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("knowledge index handling failed")


@dataclass(frozen=True, slots=True)
class KnowledgeIndexHandler:
    uow_factory: _UnitOfWorkFactory
    content_encryption: ContentEncryptionService
    key_provider: KnowledgeSearchKeyProvider
    service_actor_id: UUID
    uuid_factory: _UuidFactory

    async def handle(self, *, job: OutboxJob) -> None:
        if job.tenant_id is None:
            raise KnowledgeIndexHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )
        if job.reference.resource_type != "knowledge_document_version":
            raise KnowledgeIndexHandlerError(
                error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                permanent=True,
            )

        tenant_id = job.tenant_id
        version_id = job.reference.resource_id
        occurred_at = job.processing_started_at or job.created_at
        audit_context = AuditContext(correlation_id=job.id)

        uow = self.uow_factory()
        async with uow:
            version = await uow.knowledge_document_versions.get_by_id(
                tenant_id=tenant_id,
                version_id=version_id,
            )
            if version is None:
                raise KnowledgeIndexHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )
            if version.status == "indexed":
                return
            if version.status != "approved":
                raise KnowledgeIndexHandlerError(
                    error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                    permanent=True,
                )

        try:
            decrypted = await self.content_encryption.load_and_decrypt(
                tenant_id=tenant_id,
                content_id=version.content_id,
                purpose=ContentAccessPurpose.KNOWLEDGE_RETRIEVAL,
                occurred_at=occurred_at,
                audit_context=audit_context,
                actor_type=AuditActorType.SERVICE,
                actor_id=self.service_actor_id,
                audit_event_id=self.uuid_factory(),
            )
        except ContentEncryptionUnavailableError as error:
            raise KnowledgeIndexHandlerError(
                error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                permanent=False,
            ) from error

        if decrypted.kind is not EncryptedContentKind.KNOWLEDGE_DOCUMENT:
            raise KnowledgeIndexHandlerError(
                error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                permanent=True,
            )
        if decrypted.encoding is not ContentEncoding.UTF8:
            raise KnowledgeIndexHandlerError(
                error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                permanent=True,
            )

        chunks = chunk_text_with_overlap(text=decrypted.as_utf8_text())
        if not chunks:
            raise KnowledgeIndexHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )

        uow = self.uow_factory()
        async with uow:
            latest = await uow.knowledge_document_versions.get_by_id_for_update(
                tenant_id=tenant_id,
                version_id=version_id,
            )
            if latest is None:
                raise KnowledgeIndexHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )
            if latest.status == "indexed":
                return
            if latest.status != "approved":
                raise KnowledgeIndexHandlerError(
                    error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                    permanent=True,
                )

            chunk_records = []
            for chunk in chunks:
                chunk_id = self.uuid_factory()
                chunk_bytes = chunk.text.encode("utf-8")
                encrypted_chunk = await self.content_encryption.encrypt_and_persist(
                    uow,
                    content_id=self.uuid_factory(),
                    tenant_id=tenant_id,
                    kind=EncryptedContentKind.KNOWLEDGE_CHUNK,
                    encoding=ContentEncoding.UTF8,
                    plaintext=chunk_bytes,
                    created_at=occurred_at,
                )
                chunk_records.append(
                    KnowledgeChunkRecord(
                        id=chunk_id,
                        tenant_id=tenant_id,
                        document_version_id=latest.id,
                        content_id=encrypted_chunk.id,
                        position=chunk.position,
                        status="active",
                        chunk_sha256_digest=sha256(chunk_bytes).digest(),
                        token_count=max(1, len(chunk.text.split())),
                        created_at=occurred_at,
                    )
                )
            await uow.knowledge_chunks.revoke_by_document_version(
                tenant_id=tenant_id,
                document_version_id=latest.id,
            )
            await uow.knowledge_chunks.add_many(chunks=tuple(chunk_records))
            for chunk_record, chunk_slice in zip(chunk_records, chunks, strict=True):
                indexed_terms = build_chunk_term_index(
                    tenant_id=tenant_id,
                    chunk_text=chunk_slice.text,
                    key_provider=self.key_provider,
                )
                terms = tuple(
                    KnowledgeChunkTermRecord(
                        chunk_id=chunk_record.id,
                        tenant_id=tenant_id,
                        term_digest=term.term_digest,
                        weight_basis_points=term.weight_basis_points,
                    )
                    for term in indexed_terms
                )
                await uow.knowledge_chunk_terms.replace_for_chunk(
                    tenant_id=tenant_id,
                    chunk_id=chunk_record.id,
                    terms=terms,
                )
            updated = await uow.knowledge_document_versions.mark_indexed(
                tenant_id=tenant_id,
                version_id=latest.id,
                indexed_at=occurred_at,
            )
            await append_required_audit_event(
                uow.audit_events,
                knowledge_version_indexed_event(
                    tenant_id=tenant_id,
                    version_id=updated.id,
                    version_number=updated.version_number,
                    chunk_count=len(chunk_records),
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self.service_actor_id,
                    event_id=self.uuid_factory(),
                ),
            )
            await uow.commit()
