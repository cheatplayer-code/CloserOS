"""Integration tests for `knowledge.index` outbox handler."""

from __future__ import annotations

import asyncio
from itertools import count
from typing import Any
from uuid import UUID

import pytest
from closeros.application.knowledge_index_handler import (
    KnowledgeIndexHandler,
    KnowledgeIndexHandlerError,
)
from closeros.application.knowledge_persistence import (
    KnowledgeDocumentRecord,
    KnowledgeDocumentVersionRecord,
)
from closeros.application.knowledge_search_key import DevKnowledgeSearchKeyProvider
from closeros.domain.encrypted_content import ContentEncoding, EncryptedContentKind
from closeros.domain.outbox import (
    OutboxErrorCode,
    OutboxJobKind,
    OutboxJobReference,
    build_outbox_job,
)

from tests.encryption_support import NOW, SERVICE_ID, build_content_encryption_service
from tests.tenant_persistence_support import TENANT_A_ID, synthetic_tenant

pytestmark = pytest.mark.nopq_persistence

DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000301")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000302")
CONTENT_ID = UUID("00000000-0000-0000-0000-000000000303")
JOB_ID = UUID("00000000-0000-0000-0000-000000000304")
_UUID_COUNTER = count(0x310)


def _next_uuid() -> UUID:
    return UUID(int=next(_UUID_COUNTER))


def _job(
    *, resource_type: str = "knowledge_document_version", resource_id: UUID = VERSION_ID
) -> object:
    return build_outbox_job(
        job_id=JOB_ID,
        tenant_id=TENANT_A_ID,
        job_kind=OutboxJobKind.KNOWLEDGE_INDEX,
        reference=OutboxJobReference(
            tenant_id=TENANT_A_ID,
            resource_type=resource_type,
            resource_id=resource_id,
            schema_version=1,
        ),
        deduplication_key="knowledge_index_test_job",
        created_at=NOW,
    )


async def _seed_approved_version(integrated_uow_factory: Any, *, plaintext: bytes) -> None:
    service = build_content_encryption_service(integrated_uow_factory)
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant())
        await service.encrypt_and_persist(
            uow,
            content_id=CONTENT_ID,
            tenant_id=TENANT_A_ID,
            kind=EncryptedContentKind.KNOWLEDGE_DOCUMENT,
            encoding=ContentEncoding.UTF8,
            plaintext=plaintext,
            created_at=NOW,
        )
        await uow.knowledge_documents.add(
            KnowledgeDocumentRecord(
                id=DOCUMENT_ID,
                tenant_id=TENANT_A_ID,
                source_type="upload",
                external_reference="kb_sales_playbook",
                status="active",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await uow.knowledge_document_versions.add(
            KnowledgeDocumentVersionRecord(
                id=VERSION_ID,
                tenant_id=TENANT_A_ID,
                document_id=DOCUMENT_ID,
                version_number=1,
                status="approved",
                content_id=CONTENT_ID,
                content_sha256_digest=b"\x00" * 32,
                effective_from=NOW,
                effective_to=None,
                created_at=NOW,
                approved_at=NOW,
                indexed_at=None,
                revoked_at=None,
            )
        )
        await uow.commit()


def _handler(integrated_uow_factory: Any) -> KnowledgeIndexHandler:
    return KnowledgeIndexHandler(
        uow_factory=integrated_uow_factory,
        content_encryption=build_content_encryption_service(integrated_uow_factory),
        key_provider=DevKnowledgeSearchKeyProvider(),
        service_actor_id=SERVICE_ID,
        uuid_factory=_next_uuid,
    )


def test_handler_indexes_approved_version_and_creates_chunks(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_approved_version(
            integrated_uow_factory,
            plaintext=b"Synthetic sales guidance. Confirm next action and owner.",
        )
        handler = _handler(integrated_uow_factory)
        await handler.handle(job=_job())  # type: ignore[arg-type]
        uow = integrated_uow_factory()
        async with uow:
            version = await uow.knowledge_document_versions.get_by_id(
                tenant_id=TENANT_A_ID,
                version_id=VERSION_ID,
            )
            chunks = await uow.knowledge_chunks.list_by_document_version(
                tenant_id=TENANT_A_ID,
                document_version_id=VERSION_ID,
            )
        assert version is not None
        assert version.status == "indexed"
        assert len(chunks) >= 1

    asyncio.run(exercise())


def test_handler_is_idempotent_when_version_already_indexed(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_approved_version(
            integrated_uow_factory,
            plaintext=b"Synthetic KB v1",
        )
        handler = _handler(integrated_uow_factory)
        await handler.handle(job=_job())  # type: ignore[arg-type]
        await handler.handle(job=_job())  # type: ignore[arg-type]
        uow = integrated_uow_factory()
        async with uow:
            chunks = await uow.knowledge_chunks.list_by_document_version(
                tenant_id=TENANT_A_ID,
                document_version_id=VERSION_ID,
            )
        assert chunks

    asyncio.run(exercise())


def test_handler_rejects_unsupported_resource_type(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        handler = _handler(integrated_uow_factory)
        with pytest.raises(KnowledgeIndexHandlerError) as error:
            await handler.handle(job=_job(resource_type="message"))  # type: ignore[arg-type]
        assert error.value.error_code is OutboxErrorCode.UNSUPPORTED_OPERATION
        assert error.value.permanent is True

    asyncio.run(exercise())


def test_handler_rejects_missing_version(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        handler = _handler(integrated_uow_factory)
        with pytest.raises(KnowledgeIndexHandlerError) as error:
            await handler.handle(job=_job(resource_id=UUID("00000000-0000-0000-0000-000000000399")))  # type: ignore[arg-type]
        assert error.value.error_code is OutboxErrorCode.RESOURCE_UNAVAILABLE
        assert error.value.permanent is True

    asyncio.run(exercise())


def test_handler_rejects_empty_chunk_result(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_approved_version(integrated_uow_factory, plaintext=b"   ")
        handler = _handler(integrated_uow_factory)
        with pytest.raises(KnowledgeIndexHandlerError) as error:
            await handler.handle(job=_job())  # type: ignore[arg-type]
        assert error.value.error_code is OutboxErrorCode.MALFORMED_PROVIDER_EVENT
        assert error.value.permanent is True

    asyncio.run(exercise())
