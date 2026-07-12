"""Integration tests for CSV import outbox processor."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from closeros.application.audit_recording import AuditContext
from closeros.application.csv_import_processor import CsvImportProcessor
from closeros.application.csv_import_service import CsvImportService
from closeros.domain.audit import AuditActorType
from closeros.domain.csv_import import (
    CsvColumnMapping,
    CsvDelimiter,
    CsvImportStatus,
    CsvSourceEncoding,
)
from closeros.domain.outbox import OutboxJobKind, OutboxJobReference, build_outbox_job
from closeros.infrastructure.noop_import_content_scanner import NoOpImportContentScanner

from tests.encryption_support import NOW, SERVICE_ID, build_content_encryption_service
from tests.ingestion_support import (
    default_csv_mapping,
    sample_csv_bytes,
    synthetic_webhook_connection,
)
from tests.tenant_persistence_support import TENANT_A_ID, USER_ID, synthetic_tenant

pytestmark = pytest.mark.jk_persistence


async def _seed_import_batch(integrated_uow_factory: Any) -> tuple[Any, Any]:
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant())
        await uow.channel_connections.add(synthetic_webhook_connection())
        await uow.commit()

    service = CsvImportService(
        uow_factory=integrated_uow_factory,
        content_encryption=build_content_encryption_service(integrated_uow_factory),
        content_scanner=NoOpImportContentScanner(),
        uuid_factory=uuid4,
    )
    preview = await service.preview_upload(
        tenant_id=TENANT_A_ID,
        channel_connection_id=synthetic_webhook_connection().id,
        creator_user_id=USER_ID,
        csv_bytes=sample_csv_bytes(),
        delimiter=CsvDelimiter.COMMA,
        source_encoding=CsvSourceEncoding.UTF8,
        lawful_source_confirmed_at=NOW,
        audit_context=AuditContext(correlation_id=uuid4()),
        actor_type=AuditActorType.USER,
        actor_id=USER_ID,
    )
    started = await service.start_import(
        tenant_id=TENANT_A_ID,
        import_id=preview.import_id,
        mapping=CsvColumnMapping.from_dict(default_csv_mapping()),
        audit_context=AuditContext(correlation_id=uuid4()),
        actor_type=AuditActorType.USER,
        actor_id=USER_ID,
        occurred_at=NOW,
    )
    return preview.import_id, started.outbox_job_id


async def _publish_outbox_job(integrated_uow_factory: Any) -> None:
    from closeros.application.outbox_publisher import OutboxPublisherService

    class _NoQueue:
        async def publish_job_id(self, *, job_id: object) -> None:
            return None

    uow = integrated_uow_factory()
    async with uow:
        publisher = OutboxPublisherService(
            outbox_jobs=uow.outbox_jobs,
            outbox_job_attempts=uow.outbox_job_attempts,
            queue_publisher=_NoQueue(),
            worker_id="csv-import-test",
        )
        await publisher.publish_batch(now=NOW, batch_size=10)
        await uow.commit()


def test_csv_import_processor_completes_batch(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        import_id, outbox_job_id = await _seed_import_batch(integrated_uow_factory)
        processor = CsvImportProcessor(
            uow_factory=integrated_uow_factory,
            content_encryption=build_content_encryption_service(integrated_uow_factory),
            service_actor_id=SERVICE_ID,
            uuid_factory=uuid4,
        )
        job = build_outbox_job(
            job_id=outbox_job_id,
            tenant_id=TENANT_A_ID,
            job_kind=OutboxJobKind.CSV_IMPORT,
            reference=OutboxJobReference(
                tenant_id=TENANT_A_ID,
                resource_type="csv_import_batch",
                resource_id=import_id,
                schema_version=1,
            ),
            deduplication_key=f"csv_import_{import_id}",
            created_at=NOW,
        )
        await _publish_outbox_job(integrated_uow_factory)
        claim_uow = integrated_uow_factory()
        async with claim_uow:
            claimed = await claim_uow.outbox_jobs.claim_for_processing(
                job_id=job.id,
                worker_id="csv-import-test",
                now=NOW,
            )
            assert claimed is not None
            await processor.handle(job=claimed)
            await claim_uow.commit()
        verify_uow = integrated_uow_factory()
        async with verify_uow:
            batch = await verify_uow.csv_import_batches.get_by_id(
                tenant_id=TENANT_A_ID,
                import_id=import_id,
            )
            assert batch is not None
            assert batch.status in {
                CsvImportStatus.COMPLETED,
                CsvImportStatus.COMPLETED_WITH_ERRORS,
            }
            thread = await verify_uow.conversation_threads.get_by_external_conversation_id(
                tenant_id=TENANT_A_ID,
                channel_connection_id=synthetic_webhook_connection().id,
                external_conversation_id="conv-csv-001",
            )
            assert thread is not None

    asyncio.run(exercise())


def test_csv_import_processor_is_resumable(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        import_id, outbox_job_id = await _seed_import_batch(integrated_uow_factory)
        processor = CsvImportProcessor(
            uow_factory=integrated_uow_factory,
            content_encryption=build_content_encryption_service(integrated_uow_factory),
            service_actor_id=SERVICE_ID,
            uuid_factory=uuid4,
        )
        job = build_outbox_job(
            job_id=outbox_job_id,
            tenant_id=TENANT_A_ID,
            job_kind=OutboxJobKind.CSV_IMPORT,
            reference=OutboxJobReference(
                tenant_id=TENANT_A_ID,
                resource_type="csv_import_batch",
                resource_id=import_id,
                schema_version=1,
            ),
            deduplication_key=f"csv_import_{import_id}",
            created_at=NOW,
        )
        for _ in range(2):
            await _publish_outbox_job(integrated_uow_factory)
            claim_uow = integrated_uow_factory()
            async with claim_uow:
                claimed = await claim_uow.outbox_jobs.claim_for_processing(
                    job_id=job.id,
                    worker_id="csv-import-test",
                    now=NOW,
                )
                if claimed is not None:
                    await processor.handle(job=claimed)
                    await claim_uow.commit()
        verify_uow = integrated_uow_factory()
        async with verify_uow:
            batch = await verify_uow.csv_import_batches.get_by_id(
                tenant_id=TENANT_A_ID,
                import_id=import_id,
            )
            assert batch is not None
            assert batch.succeeded_count == 1

    asyncio.run(exercise())
