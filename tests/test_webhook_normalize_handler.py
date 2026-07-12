"""Integration tests for webhook normalization outbox handler."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from closeros.application.atomic_content_commands import AtomicContentCommandService
from closeros.application.audit_recording import AuditContext
from closeros.application.provider_adapter_registry import ProviderAdapterRegistry
from closeros.application.webhook_ingestion import WebhookIngestionService
from closeros.application.webhook_normalize_handler import WebhookNormalizeHandler
from closeros.domain.canonical_enums import ProviderKind, WebhookProcessingStatus
from closeros.domain.outbox import (
    OutboxJobKind,
    OutboxJobReference,
    OutboxJobState,
    build_outbox_job,
)
from closeros.infrastructure.in_memory_webhook_rate_limiter import InMemoryWebhookRateLimiter
from closeros.infrastructure.synthetic_hmac_adapter import SyntheticHmacWebhookAdapter

from tests.encryption_support import NOW, SERVICE_ID, build_content_encryption_service
from tests.ingestion_support import (
    SYNTHETIC_CONNECTION_ID,
    SYNTHETIC_EXTERNAL_EVENT_ID,
    SYNTHETIC_WEBHOOK_SECRET,
    build_synthetic_message_received_payload,
    build_synthetic_webhook_headers,
    synthetic_webhook_connection,
)
from tests.tenant_persistence_support import TENANT_A_ID, synthetic_tenant

pytestmark = pytest.mark.jk_persistence

CORRELATION_ID = UUID("00000000-0000-0000-0000-000000000999")


async def _seed_and_accept(integrated_uow_factory: Any) -> UUID:
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant())
        await uow.channel_connections.add(synthetic_webhook_connection())
        await uow.commit()

    content_encryption = build_content_encryption_service(integrated_uow_factory)
    atomic_commands = AtomicContentCommandService(
        uow_factory=integrated_uow_factory,
        content_encryption=content_encryption,
    )
    ingestion = WebhookIngestionService(
        uow_factory=integrated_uow_factory,
        atomic_commands=atomic_commands,
        adapter_registry=ProviderAdapterRegistry(
            adapters=(SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET),),
        ),
        rate_limiter=InMemoryWebhookRateLimiter(),
        service_actor_id=SERVICE_ID,
        uuid_factory=uuid4,
    )
    body = build_synthetic_message_received_payload()
    headers = build_synthetic_webhook_headers(body=body)
    result = await ingestion.accept_provider_webhook(
        provider_kind=ProviderKind.SYNTHETIC,
        connection_id=SYNTHETIC_CONNECTION_ID,
        raw_body=body,
        headers=headers,
        content_length=len(body),
        audit_context=AuditContext(correlation_id=CORRELATION_ID),
        received_at=NOW,
    )
    assert result.accepted is True

    uow = integrated_uow_factory()
    async with uow:
        event = await uow.webhook_events.get_by_external_event_id(
            tenant_id=TENANT_A_ID,
            channel_connection_id=SYNTHETIC_CONNECTION_ID,
            external_event_id=SYNTHETIC_EXTERNAL_EVENT_ID,
        )
        assert event is not None
        event_id: UUID = event.id
        return event_id


async def _publish_job(integrated_uow_factory: Any, *, job_id: Any) -> None:
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
            worker_id="normalize-test",
        )
        await publisher.publish_batch(now=NOW, batch_size=10)
        await uow.commit()


def _build_handler(integrated_uow_factory: Any) -> WebhookNormalizeHandler:
    content_encryption = build_content_encryption_service(integrated_uow_factory)
    return WebhookNormalizeHandler(
        uow_factory=integrated_uow_factory,
        content_encryption=content_encryption,
        adapter_registry=ProviderAdapterRegistry(
            adapters=(SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET),),
        ),
        atomic_commands=AtomicContentCommandService(
            uow_factory=integrated_uow_factory,
            content_encryption=content_encryption,
        ),
        service_actor_id=SERVICE_ID,
        uuid_factory=uuid4,
    )


async def _pending_job_for_event(integrated_uow_factory: Any, *, event_id: UUID) -> Any:
    from closeros.application.outbox_persistence import OutboxReconciliationFilter

    uow = integrated_uow_factory()
    async with uow:
        jobs = await uow.outbox_jobs.list_by_state(
            state=OutboxJobState.PENDING,
            query_filter=OutboxReconciliationFilter(limit=10),
        )
    return next(job for job in jobs if job.reference.resource_id == event_id)


def test_webhook_normalize_handler_creates_message(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        event_id = await _seed_and_accept(integrated_uow_factory)
        handler = _build_handler(integrated_uow_factory)
        job = await _pending_job_for_event(integrated_uow_factory, event_id=event_id)
        await _publish_job(integrated_uow_factory, job_id=job.id)
        claimed_uow = integrated_uow_factory()
        async with claimed_uow:
            claimed = await claimed_uow.outbox_jobs.claim_for_processing(
                job_id=job.id,
                worker_id="normalize-test",
                now=NOW,
            )
            assert claimed is not None
            await handler.handle(job=claimed)
        verify_uow = integrated_uow_factory()
        async with verify_uow:
            webhook_event = await verify_uow.webhook_events.get_by_id(
                tenant_id=TENANT_A_ID,
                event_id=event_id,
            )
            assert webhook_event is not None
            assert webhook_event.processing_status is WebhookProcessingStatus.PROCESSED
            thread = await verify_uow.conversation_threads.get_by_external_conversation_id(
                tenant_id=TENANT_A_ID,
                channel_connection_id=SYNTHETIC_CONNECTION_ID,
                external_conversation_id="conv-synthetic-001",
            )
            assert thread is not None
            message = await verify_uow.messages.get_by_external_message_id(
                tenant_id=TENANT_A_ID,
                conversation_thread_id=thread.id,
                external_message_id="msg-synthetic-001",
            )
            assert message is not None

    asyncio.run(exercise())


def test_webhook_normalize_handler_is_idempotent(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        event_id = await _seed_and_accept(integrated_uow_factory)
        handler = _build_handler(integrated_uow_factory)
        job = await _pending_job_for_event(integrated_uow_factory, event_id=event_id)
        for _ in range(2):
            await _publish_job(integrated_uow_factory, job_id=job.id)
            process_uow = integrated_uow_factory()
            async with process_uow:
                claimed = await process_uow.outbox_jobs.claim_for_processing(
                    job_id=job.id,
                    worker_id="normalize-test",
                    now=NOW,
                )
                if claimed is not None:
                    await handler.handle(job=claimed)
                    await process_uow.commit()
        verify_uow = integrated_uow_factory()
        async with verify_uow:
            thread = await verify_uow.conversation_threads.get_by_external_conversation_id(
                tenant_id=TENANT_A_ID,
                channel_connection_id=SYNTHETIC_CONNECTION_ID,
                external_conversation_id="conv-synthetic-001",
            )
            assert thread is not None
            message = await verify_uow.messages.get_by_external_message_id(
                tenant_id=TENANT_A_ID,
                conversation_thread_id=thread.id,
                external_message_id="msg-synthetic-001",
            )
            assert message is not None

    asyncio.run(exercise())


def test_webhook_normalize_handler_skips_processed_event(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        event_id = await _seed_and_accept(integrated_uow_factory)
        handler = _build_handler(integrated_uow_factory)
        mark_uow = integrated_uow_factory()
        async with mark_uow:
            await mark_uow.webhook_events.update_processing_status(
                tenant_id=TENANT_A_ID,
                event_id=event_id,
                processing_status=WebhookProcessingStatus.PROCESSED,
                processed_at=NOW,
            )
            await mark_uow.commit()
        job = build_outbox_job(
            job_id=uuid4(),
            tenant_id=TENANT_A_ID,
            job_kind=OutboxJobKind.WEBHOOK_NORMALIZE,
            reference=OutboxJobReference(
                tenant_id=TENANT_A_ID,
                resource_type="webhook_event",
                resource_id=event_id,
                schema_version=1,
            ),
            deduplication_key=f"webhook_normalize_{event_id}",
            created_at=NOW,
        )
        process_uow = integrated_uow_factory()
        async with process_uow:
            await handler.handle(job=job)

    asyncio.run(exercise())
