"""Integration tests for webhook ingestion service."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from closeros.application.atomic_content_commands import AtomicContentCommandService
from closeros.application.audit_recording import AuditContext
from closeros.application.provider_adapter_registry import ProviderAdapterRegistry
from closeros.application.webhook_ingestion import (
    WEBHOOK_DENIED_RESPONSE,
    WebhookIngestionDeniedError,
    WebhookIngestionService,
)
from closeros.domain.audit import AuditActorType
from closeros.domain.canonical_enums import ProviderKind
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


def _audit_context() -> AuditContext:
    return AuditContext(correlation_id=CORRELATION_ID)


def _build_service(
    integrated_uow_factory: Any, *, rate_limit: int = 120
) -> WebhookIngestionService:
    content_encryption = build_content_encryption_service(integrated_uow_factory)
    atomic_commands = AtomicContentCommandService(
        uow_factory=integrated_uow_factory,
        content_encryption=content_encryption,
    )
    return WebhookIngestionService(
        uow_factory=integrated_uow_factory,
        atomic_commands=atomic_commands,
        adapter_registry=ProviderAdapterRegistry(
            adapters=(SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET),),
        ),
        rate_limiter=InMemoryWebhookRateLimiter(),
        service_actor_id=SERVICE_ID,
        uuid_factory=uuid4,
        webhook_rate_limit=rate_limit,
        webhook_rate_window_seconds=60,
    )


async def _seed_connection(integrated_uow_factory: Any) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant())
        await uow.channel_connections.add(synthetic_webhook_connection())
        await uow.commit()


def test_webhook_ingestion_accepts_valid_signature(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        body = build_synthetic_message_received_payload()
        headers = build_synthetic_webhook_headers(body=body)
        result = await service.accept_provider_webhook(
            provider_kind=ProviderKind.SYNTHETIC,
            connection_id=SYNTHETIC_CONNECTION_ID,
            raw_body=body,
            headers=headers,
            content_length=len(body),
            audit_context=_audit_context(),
            received_at=NOW,
        )
        assert result.accepted is True
        assert result.duplicate is False

    asyncio.run(exercise())


def test_webhook_ingestion_rejects_invalid_signature(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        body = build_synthetic_message_received_payload()
        headers = build_synthetic_webhook_headers(body=body)
        headers["x-synthetic-signature"] = "deadbeef"
        with pytest.raises(WebhookIngestionDeniedError, match=WEBHOOK_DENIED_RESPONSE):
            await service.accept_provider_webhook(
                provider_kind=ProviderKind.SYNTHETIC,
                connection_id=SYNTHETIC_CONNECTION_ID,
                raw_body=body,
                headers=headers,
                content_length=len(body),
                audit_context=_audit_context(),
                received_at=NOW,
            )

    asyncio.run(exercise())


def test_webhook_ingestion_rejects_oversized_body(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        body = b"x" * (1024 * 1024 + 1)
        with pytest.raises(WebhookIngestionDeniedError, match=WEBHOOK_DENIED_RESPONSE):
            await service.accept_provider_webhook(
                provider_kind=ProviderKind.SYNTHETIC,
                connection_id=SYNTHETIC_CONNECTION_ID,
                raw_body=body,
                headers={},
                content_length=len(body),
                audit_context=_audit_context(),
                received_at=NOW,
            )

    asyncio.run(exercise())


def test_webhook_ingestion_rejects_unknown_provider(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        body = build_synthetic_message_received_payload()
        headers = build_synthetic_webhook_headers(body=body)
        with pytest.raises(WebhookIngestionDeniedError, match=WEBHOOK_DENIED_RESPONSE):
            await service.accept_provider_webhook(
                provider_kind=ProviderKind.WHATSAPP,
                connection_id=SYNTHETIC_CONNECTION_ID,
                raw_body=body,
                headers=headers,
                content_length=len(body),
                audit_context=_audit_context(),
                received_at=NOW,
            )

    asyncio.run(exercise())


def test_webhook_ingestion_is_idempotent(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        body = build_synthetic_message_received_payload()
        headers = build_synthetic_webhook_headers(body=body)
        now = NOW
        first = await service.accept_provider_webhook(
            provider_kind=ProviderKind.SYNTHETIC,
            connection_id=SYNTHETIC_CONNECTION_ID,
            raw_body=body,
            headers=headers,
            content_length=len(body),
            audit_context=_audit_context(),
            received_at=now,
        )
        second = await service.accept_provider_webhook(
            provider_kind=ProviderKind.SYNTHETIC,
            connection_id=SYNTHETIC_CONNECTION_ID,
            raw_body=body,
            headers=headers,
            content_length=len(body),
            audit_context=_audit_context(),
            received_at=now,
        )
        assert first.duplicate is False
        assert second.duplicate is True

    asyncio.run(exercise())


def test_webhook_ingestion_enforces_rate_limit(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory, rate_limit=1)
        body = build_synthetic_message_received_payload()
        now = NOW
        for index in range(2):
            headers = build_synthetic_webhook_headers(
                body=body,
                external_event_id=f"{SYNTHETIC_EXTERNAL_EVENT_ID}-{index}",
            )
            if index == 0:
                await service.accept_provider_webhook(
                    provider_kind=ProviderKind.SYNTHETIC,
                    connection_id=SYNTHETIC_CONNECTION_ID,
                    raw_body=body,
                    headers=headers,
                    content_length=len(body),
                    audit_context=_audit_context(),
                    received_at=now,
                )
            else:
                with pytest.raises(WebhookIngestionDeniedError, match=WEBHOOK_DENIED_RESPONSE):
                    await service.accept_provider_webhook(
                        provider_kind=ProviderKind.SYNTHETIC,
                        connection_id=SYNTHETIC_CONNECTION_ID,
                        raw_body=body,
                        headers=headers,
                        content_length=len(body),
                        audit_context=_audit_context(),
                        received_at=now,
                    )

    asyncio.run(exercise())


def test_webhook_ingestion_rejects_missing_connection(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _build_service(integrated_uow_factory)
        body = build_synthetic_message_received_payload()
        headers = build_synthetic_webhook_headers(body=body)
        with pytest.raises(WebhookIngestionDeniedError, match=WEBHOOK_DENIED_RESPONSE):
            await service.accept_provider_webhook(
                provider_kind=ProviderKind.SYNTHETIC,
                connection_id=SYNTHETIC_CONNECTION_ID,
                raw_body=body,
                headers=headers,
                content_length=len(body),
                audit_context=_audit_context(),
                received_at=NOW,
            )

    asyncio.run(exercise())


def test_webhook_ingestion_persists_outbox_job(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        from closeros.application.outbox_persistence import OutboxReconciliationFilter
        from closeros.domain.outbox import OutboxJobKind, OutboxJobState

        await _seed_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        body = build_synthetic_message_received_payload()
        headers = build_synthetic_webhook_headers(body=body)
        await service.accept_provider_webhook(
            provider_kind=ProviderKind.SYNTHETIC,
            connection_id=SYNTHETIC_CONNECTION_ID,
            raw_body=body,
            headers=headers,
            content_length=len(body),
            audit_context=_audit_context(),
            received_at=NOW,
        )
        uow = integrated_uow_factory()
        async with uow:
            jobs = await uow.outbox_jobs.list_by_state(
                state=OutboxJobState.PENDING,
                query_filter=OutboxReconciliationFilter(limit=10),
            )
        assert any(job.job_kind is OutboxJobKind.WEBHOOK_NORMALIZE for job in jobs)
        assert all(job.tenant_id == TENANT_A_ID for job in jobs)

    asyncio.run(exercise())


def test_webhook_ingestion_records_service_actor(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        from closeros.application.audit_persistence import AuditQueryFilter
        from closeros.domain.audit import AuditAction

        await _seed_connection(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        body = build_synthetic_message_received_payload()
        headers = build_synthetic_webhook_headers(body=body)
        await service.accept_provider_webhook(
            provider_kind=ProviderKind.SYNTHETIC,
            connection_id=SYNTHETIC_CONNECTION_ID,
            raw_body=body,
            headers=headers,
            content_length=len(body),
            audit_context=_audit_context(),
            received_at=NOW,
        )
        uow = integrated_uow_factory()
        async with uow:
            page = await uow.audit_events.query_page(
                query_filter=AuditQueryFilter(tenant_id=TENANT_A_ID),
                cursor=None,
                page_size=20,
            )
        accepted = [
            event
            for event in page.events
            if event.action is AuditAction.WEBHOOK_ACCEPTED
            and event.actor.actor_type is AuditActorType.SERVICE
        ]
        assert accepted
        assert accepted[0].actor.actor_id == SERVICE_ID

    asyncio.run(exercise())
