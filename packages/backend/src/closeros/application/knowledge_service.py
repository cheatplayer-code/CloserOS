"""Application orchestration for knowledge upload, approval, revocation, listing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.knowledge_audit import (
    knowledge_document_uploaded_event,
    knowledge_version_approved_event,
    knowledge_version_revoked_event,
)
from closeros.application.knowledge_persistence import (
    KnowledgeDocumentRecord,
    KnowledgeDocumentVersionRecord,
)
from closeros.domain.audit import AuditActorType
from closeros.domain.encrypted_content import (
    ContentEncoding,
    EncryptedContentKind,
    validate_plaintext_for_kind,
)
from closeros.domain.outbox import OutboxJobKind, OutboxJobReference, build_outbox_job

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]


@dataclass(frozen=True, slots=True)
class KnowledgeUploadResult:
    document_id: UUID
    version_id: UUID
    version_number: int


@dataclass(frozen=True, slots=True)
class ListedKnowledgeDocument:
    document: KnowledgeDocumentRecord
    latest_version: KnowledgeDocumentVersionRecord | None


class KnowledgeService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        content_encryption: ContentEncryptionService,
        uuid_factory: _UuidFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._content_encryption = content_encryption
        self._uuid_factory = uuid_factory

    async def upload_document(
        self,
        *,
        tenant_id: UUID,
        source_code: str,
        plaintext_text: str,
        occurred_at: datetime,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> KnowledgeUploadResult:
        plaintext_bytes = validate_plaintext_for_kind(
            kind=EncryptedContentKind.KNOWLEDGE_DOCUMENT,
            plaintext=plaintext_text.encode("utf-8"),
        )
        audit_context = AuditContext(correlation_id=self._uuid_factory())
        document_id = self._uuid_factory()
        version_id = self._uuid_factory()
        content_id = self._uuid_factory()

        uow = self._uow_factory()
        async with uow:
            encrypted = await self._content_encryption.encrypt_and_persist(
                uow,
                content_id=content_id,
                tenant_id=tenant_id,
                kind=EncryptedContentKind.KNOWLEDGE_DOCUMENT,
                encoding=ContentEncoding.UTF8,
                plaintext=plaintext_bytes,
                created_at=occurred_at,
            )
            document = KnowledgeDocumentRecord(
                id=document_id,
                tenant_id=tenant_id,
                source_type="upload",
                external_reference=source_code.strip(),
                status="active",
                created_at=occurred_at,
                updated_at=occurred_at,
            )
            await uow.knowledge_documents.add(document)
            version = KnowledgeDocumentVersionRecord(
                id=version_id,
                tenant_id=tenant_id,
                document_id=document_id,
                version_number=1,
                status="draft",
                content_id=encrypted.id,
                content_sha256_digest=sha256(plaintext_bytes).digest(),
                effective_from=occurred_at,
                effective_to=None,
                created_at=occurred_at,
                approved_at=None,
                indexed_at=None,
                revoked_at=None,
            )
            await uow.knowledge_document_versions.add(version)
            await append_required_audit_event(
                uow.audit_events,
                knowledge_document_uploaded_event(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    source_type=document.source_type,
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
        return KnowledgeUploadResult(
            document_id=document_id,
            version_id=version_id,
            version_number=1,
        )

    async def approve_version(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
        occurred_at: datetime,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> KnowledgeDocumentVersionRecord:
        audit_context = AuditContext(correlation_id=self._uuid_factory())
        uow = self._uow_factory()
        async with uow:
            version = await uow.knowledge_document_versions.get_by_id_for_update(
                tenant_id=tenant_id,
                version_id=version_id,
            )
            if version is None:
                raise ValueError("knowledge version not found")
            if version.status == "revoked":
                raise ValueError("revoked knowledge version cannot be approved")
            if version.status != "approved":
                version = await uow.knowledge_document_versions.mark_approved(
                    tenant_id=tenant_id,
                    version_id=version_id,
                    approved_at=occurred_at,
                )

            outbox_job = build_outbox_job(
                job_id=self._uuid_factory(),
                tenant_id=tenant_id,
                job_kind=OutboxJobKind.KNOWLEDGE_INDEX,
                reference=OutboxJobReference(
                    tenant_id=tenant_id,
                    resource_type="knowledge_document_version",
                    resource_id=version.id,
                    schema_version=1,
                ),
                deduplication_key=f"knowledge_index_{version.id.hex}",
                created_at=occurred_at,
            )
            await uow.outbox_jobs.get_or_create(outbox_job)
            await append_required_audit_event(
                uow.audit_events,
                knowledge_version_approved_event(
                    tenant_id=tenant_id,
                    version_id=version.id,
                    version_number=version.version_number,
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
            return version

    async def revoke_version(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
        occurred_at: datetime,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> KnowledgeDocumentVersionRecord:
        audit_context = AuditContext(correlation_id=self._uuid_factory())
        uow = self._uow_factory()
        async with uow:
            version = await uow.knowledge_document_versions.get_by_id_for_update(
                tenant_id=tenant_id,
                version_id=version_id,
            )
            if version is None:
                raise ValueError("knowledge version not found")
            if version.status == "revoked":
                return version
            version = await uow.knowledge_document_versions.mark_revoked(
                tenant_id=tenant_id,
                version_id=version.id,
                revoked_at=occurred_at,
            )
            revoked_count = await uow.knowledge_chunks.revoke_by_document_version(
                tenant_id=tenant_id,
                document_version_id=version.id,
            )
            await append_required_audit_event(
                uow.audit_events,
                knowledge_version_revoked_event(
                    tenant_id=tenant_id,
                    version_id=version.id,
                    version_number=version.version_number,
                    revoked_chunk_count=revoked_count,
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
            return version

    async def list_documents(
        self,
        *,
        tenant_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ListedKnowledgeDocument, ...]:
        uow = self._uow_factory()
        async with uow:
            documents = await uow.knowledge_documents.list_by_tenant(
                tenant_id=tenant_id,
                limit=limit,
                offset=offset,
            )
            result: list[ListedKnowledgeDocument] = []
            for document in documents:
                versions = await uow.knowledge_document_versions.list_by_document(
                    tenant_id=tenant_id,
                    document_id=document.id,
                    limit=1,
                )
                latest = versions[0] if versions else None
                result.append(ListedKnowledgeDocument(document=document, latest_version=latest))
            return tuple(result)
