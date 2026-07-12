"""Integration tests for CSV import application service."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from closeros.application.audit_recording import AuditContext
from closeros.application.csv_import_service import (
    CsvImportService,
    CsvImportValidationError,
)
from closeros.domain.audit import AuditActorType
from closeros.domain.csv_import import (
    CsvColumnMapping,
    CsvDelimiter,
    CsvImportStatus,
    CsvSourceEncoding,
)
from closeros.domain.encrypted_content import EncryptedContentKind
from closeros.infrastructure.noop_import_content_scanner import NoOpImportContentScanner

from tests.encryption_support import NOW, build_content_encryption_service
from tests.ingestion_support import (
    default_csv_mapping,
    sample_csv_bytes,
    synthetic_webhook_connection,
)
from tests.tenant_persistence_support import TENANT_A_ID, USER_ID, synthetic_tenant

pytestmark = pytest.mark.jk_persistence

CORRELATION_ID = UUID("00000000-0000-0000-0000-000000000999")


def _audit_context() -> AuditContext:
    return AuditContext(correlation_id=CORRELATION_ID)


def _build_service(integrated_uow_factory: Any) -> CsvImportService:
    return CsvImportService(
        uow_factory=integrated_uow_factory,
        content_encryption=build_content_encryption_service(integrated_uow_factory),
        content_scanner=NoOpImportContentScanner(),
        uuid_factory=uuid4,
    )


async def _seed_tenant_and_connection(integrated_uow_factory: Any) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant())
        await uow.channel_connections.add(synthetic_webhook_connection())
        await uow.commit()


def test_csv_import_preview_parses_headers(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        preview = await service.preview_upload(
            tenant_id=TENANT_A_ID,
            channel_connection_id=synthetic_webhook_connection().id,
            creator_user_id=USER_ID,
            csv_bytes=sample_csv_bytes(),
            delimiter=CsvDelimiter.COMMA,
            source_encoding=CsvSourceEncoding.UTF8,
            lawful_source_confirmed_at=NOW,
            audit_context=_audit_context(),
            actor_type=AuditActorType.USER,
            actor_id=USER_ID,
        )
        assert preview.total_rows == 1
        assert len(preview.columns) == 7

    asyncio.run(exercise())


def test_csv_import_preview_encrypts_source(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        preview = await service.preview_upload(
            tenant_id=TENANT_A_ID,
            channel_connection_id=synthetic_webhook_connection().id,
            creator_user_id=USER_ID,
            csv_bytes=sample_csv_bytes(),
            delimiter=CsvDelimiter.COMMA,
            source_encoding=CsvSourceEncoding.UTF8,
            lawful_source_confirmed_at=NOW,
            audit_context=_audit_context(),
            actor_type=AuditActorType.USER,
            actor_id=USER_ID,
        )
        uow = integrated_uow_factory()
        async with uow:
            batch = await uow.csv_import_batches.get_by_id(
                tenant_id=TENANT_A_ID,
                import_id=preview.import_id,
            )
            assert batch is not None
            encrypted = await uow.encrypted_contents.get_by_id(
                tenant_id=TENANT_A_ID,
                content_id=batch.source_content_id,
            )
            assert encrypted is not None
            assert encrypted.kind is EncryptedContentKind.CSV_IMPORT

    asyncio.run(exercise())


def test_csv_import_start_enqueues_job(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        from closeros.application.outbox_persistence import OutboxReconciliationFilter
        from closeros.domain.outbox import OutboxJobKind, OutboxJobState

        await _seed_tenant_and_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        preview = await service.preview_upload(
            tenant_id=TENANT_A_ID,
            channel_connection_id=synthetic_webhook_connection().id,
            creator_user_id=USER_ID,
            csv_bytes=sample_csv_bytes(),
            delimiter=CsvDelimiter.COMMA,
            source_encoding=CsvSourceEncoding.UTF8,
            lawful_source_confirmed_at=NOW,
            audit_context=_audit_context(),
            actor_type=AuditActorType.USER,
            actor_id=USER_ID,
        )
        started = await service.start_import(
            tenant_id=TENANT_A_ID,
            import_id=preview.import_id,
            mapping=CsvColumnMapping.from_dict(default_csv_mapping()),
            audit_context=_audit_context(),
            actor_type=AuditActorType.USER,
            actor_id=USER_ID,
            occurred_at=NOW,
        )
        uow = integrated_uow_factory()
        async with uow:
            job = await uow.outbox_jobs.get_by_id(job_id=started.outbox_job_id)
            assert job is not None
            assert job.job_kind is OutboxJobKind.CSV_IMPORT
            pending = await uow.outbox_jobs.list_by_state(
                state=OutboxJobState.PENDING,
                query_filter=OutboxReconciliationFilter(limit=10),
            )
            assert any(item.id == started.outbox_job_id for item in pending)

    asyncio.run(exercise())


def test_csv_import_preview_rejects_empty_body(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        with pytest.raises(CsvImportValidationError):
            await service.preview_upload(
                tenant_id=TENANT_A_ID,
                channel_connection_id=synthetic_webhook_connection().id,
                creator_user_id=USER_ID,
                csv_bytes=b"",
                delimiter=CsvDelimiter.COMMA,
                source_encoding=CsvSourceEncoding.UTF8,
                lawful_source_confirmed_at=NOW,
                audit_context=_audit_context(),
                actor_type=AuditActorType.USER,
                actor_id=USER_ID,
            )

    asyncio.run(exercise())


def test_csv_import_status_returns_batch(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        preview = await service.preview_upload(
            tenant_id=TENANT_A_ID,
            channel_connection_id=synthetic_webhook_connection().id,
            creator_user_id=USER_ID,
            csv_bytes=sample_csv_bytes(),
            delimiter=CsvDelimiter.COMMA,
            source_encoding=CsvSourceEncoding.UTF8,
            lawful_source_confirmed_at=NOW,
            audit_context=_audit_context(),
            actor_type=AuditActorType.USER,
            actor_id=USER_ID,
        )
        status = await service.get_status(tenant_id=TENANT_A_ID, import_id=preview.import_id)
        assert status.status is CsvImportStatus.UPLOADED
        assert status.total_rows == 1

    asyncio.run(exercise())


def test_csv_import_cancel_updates_status(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        preview = await service.preview_upload(
            tenant_id=TENANT_A_ID,
            channel_connection_id=synthetic_webhook_connection().id,
            creator_user_id=USER_ID,
            csv_bytes=sample_csv_bytes(),
            delimiter=CsvDelimiter.COMMA,
            source_encoding=CsvSourceEncoding.UTF8,
            lawful_source_confirmed_at=NOW,
            audit_context=_audit_context(),
            actor_type=AuditActorType.USER,
            actor_id=USER_ID,
        )
        await service.cancel_import(
            tenant_id=TENANT_A_ID,
            import_id=preview.import_id,
            audit_context=_audit_context(),
            actor_type=AuditActorType.USER,
            actor_id=USER_ID,
            occurred_at=NOW,
        )
        status = await service.get_status(tenant_id=TENANT_A_ID, import_id=preview.import_id)
        assert status.status is CsvImportStatus.CANCELLED

    asyncio.run(exercise())
