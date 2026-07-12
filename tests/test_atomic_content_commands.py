"""PostgreSQL integration tests for atomic encrypted-content commands."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from closeros.application.atomic_content_commands import (
    AtomicContentCommandService,
    AtomicContentCommandUnavailableError,
)
from closeros.application.audit_persistence import AuditQueryFilter
from closeros.application.audit_recording import AuditContext
from closeros.domain.audit import AuditAction, AuditActorType
from closeros.domain.canonical_enums import MessageDirection, ParticipantSenderType
from closeros.domain.encrypted_content import ContentEncoding
from closeros.domain.outbox import OutboxJobKind, OutboxJobState

from tests.canonical_persistence_support import (
    CONTENT_A_ID,
    CONTENT_B_ID,
    EDIT_EVENT_A_ID,
    MESSAGE_A_ID,
    MESSAGE_B_ID,
    NOW,
    SALES_CASE_A_ID,
    THREAD_A_ID,
    WEBHOOK_EVENT_A_ID,
    synthetic_adapter_metadata,
    synthetic_channel_connection,
    synthetic_conversation_thread,
    synthetic_message,
    synthetic_sales_case,
    synthetic_webhook_event,
)
from tests.encryption_support import (
    AUDIT_EVENT_ID,
    OUTBOX_JOB_B_ID,
    OUTBOX_JOB_ID,
    SERVICE_ID,
    SYNTHETIC_PLAINTEXT_JSON,
    SYNTHETIC_PLAINTEXT_UTF8,
    build_content_encryption_service,
)
from tests.tenant_persistence_support import TENANT_A_ID, synthetic_tenant

pytestmark = pytest.mark.hi_persistence

CORRELATION_ID = UUID("00000000-0000-0000-0000-000000000999")


def _audit_context() -> AuditContext:
    return AuditContext(correlation_id=CORRELATION_ID)


async def _seed_platform_graph(integrated_uow_factory: Any) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant())
        await uow.channel_connections.add(synthetic_channel_connection())
        await uow.sales_cases.add(synthetic_sales_case())
        await uow.conversation_threads.add(
            synthetic_conversation_thread(sales_case_id=SALES_CASE_A_ID, lifecycle_status=None)
        )
        await uow.webhook_events.append(synthetic_webhook_event())
        await uow.commit()


def _build_service(integrated_uow_factory: Any) -> AtomicContentCommandService:
    return AtomicContentCommandService(
        uow_factory=integrated_uow_factory,
        content_encryption=build_content_encryption_service(integrated_uow_factory),
    )


def test_store_raw_message_atomic_persistence(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        result = await service.store_raw_message(
            tenant_id=TENANT_A_ID,
            content_id=CONTENT_A_ID,
            message_id=MESSAGE_A_ID,
            outbox_job_id=OUTBOX_JOB_ID,
            audit_event_id=AUDIT_EVENT_ID,
            conversation_thread_id=THREAD_A_ID,
            external_message_id="msg-atomic-001",
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            sent_at=NOW,
            received_at=NOW,
            reply_to_message_id=None,
            adapter_metadata=synthetic_adapter_metadata(),
            plaintext=SYNTHETIC_PLAINTEXT_UTF8,
            created_at=NOW,
            occurred_at=NOW,
            audit_context=_audit_context(),
            actor_type=AuditActorType.SERVICE,
            actor_id=SERVICE_ID,
        )
        assert result.content_id == CONTENT_A_ID
        uow = integrated_uow_factory()
        async with uow:
            message = await uow.messages.get_by_id(
                tenant_id=TENANT_A_ID,
                message_id=MESSAGE_A_ID,
            )
            encrypted = await uow.encrypted_contents.get_by_id(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_A_ID,
            )
            job = await uow.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_ID)
        assert message is not None
        assert encrypted is not None
        assert job is not None
        assert job.job_kind is OutboxJobKind.CONTENT_REDACT
        assert job.state is OutboxJobState.PENDING

    asyncio.run(exercise())


def test_store_raw_message_rolls_back_on_duplicate_message(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            await uow.messages.append(
                synthetic_message(content_id=None, external_message_id="msg-atomic-dup")
            )
            await uow.commit()
        service = _build_service(integrated_uow_factory)
        with pytest.raises(AtomicContentCommandUnavailableError):
            await service.store_raw_message(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_A_ID,
                message_id=MESSAGE_A_ID,
                outbox_job_id=OUTBOX_JOB_ID,
                audit_event_id=AUDIT_EVENT_ID,
                conversation_thread_id=THREAD_A_ID,
                external_message_id="msg-atomic-dup",
                sender_type=ParticipantSenderType.CUSTOMER,
                direction=MessageDirection.INBOUND,
                sent_at=NOW,
                received_at=NOW,
                reply_to_message_id=None,
                adapter_metadata=synthetic_adapter_metadata(),
                plaintext=SYNTHETIC_PLAINTEXT_UTF8,
                created_at=NOW,
                occurred_at=NOW,
                audit_context=_audit_context(),
                actor_type=AuditActorType.SERVICE,
                actor_id=SERVICE_ID,
            )
        lookup = integrated_uow_factory()
        async with lookup:
            encrypted = await lookup.encrypted_contents.get_by_id(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_A_ID,
            )
            job = await lookup.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_ID)
        assert encrypted is None
        assert job is None

    asyncio.run(exercise())


def test_store_message_edit_atomic_persistence(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            await uow.messages.append(synthetic_message(content_id=None))
            await uow.commit()
        service = _build_service(integrated_uow_factory)
        result = await service.store_message_edit(
            tenant_id=TENANT_A_ID,
            content_id=CONTENT_B_ID,
            edit_event_id=EDIT_EVENT_A_ID,
            message_id=MESSAGE_A_ID,
            outbox_job_id=OUTBOX_JOB_B_ID,
            audit_event_id=uuid4(),
            external_event_id="edit-atomic-001",
            occurred_at=NOW,
            adapter_metadata=synthetic_adapter_metadata(),
            plaintext=SYNTHETIC_PLAINTEXT_UTF8,
            created_at=NOW,
            audit_context=_audit_context(),
            actor_type=AuditActorType.SERVICE,
            actor_id=SERVICE_ID,
        )
        assert result.edit_event_id == EDIT_EVENT_A_ID
        lookup = integrated_uow_factory()
        async with lookup:
            edit_event = await lookup.message_edit_events.get_by_id(
                tenant_id=TENANT_A_ID,
                event_id=EDIT_EVENT_A_ID,
            )
            encrypted = await lookup.encrypted_contents.get_by_id(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_B_ID,
            )
        assert edit_event is not None
        assert encrypted is not None

    asyncio.run(exercise())


def test_attach_provider_payload_atomic_persistence(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        result = await service.attach_provider_payload(
            tenant_id=TENANT_A_ID,
            content_id=CONTENT_A_ID,
            webhook_event_id=WEBHOOK_EVENT_A_ID,
            outbox_job_id=OUTBOX_JOB_ID,
            audit_event_id=AUDIT_EVENT_ID,
            plaintext=SYNTHETIC_PLAINTEXT_JSON,
            encoding=ContentEncoding.JSON,
            created_at=NOW,
            occurred_at=NOW,
            audit_context=_audit_context(),
            actor_type=AuditActorType.SERVICE,
            actor_id=SERVICE_ID,
        )
        assert result.webhook_event_id == WEBHOOK_EVENT_A_ID
        lookup = integrated_uow_factory()
        async with lookup:
            event = await lookup.webhook_events.get_by_id(
                tenant_id=TENANT_A_ID,
                event_id=WEBHOOK_EVENT_A_ID,
            )
            encrypted = await lookup.encrypted_contents.get_by_id(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_A_ID,
            )
            job = await lookup.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_ID)
        assert event is not None
        assert event.encrypted_payload_content_id == CONTENT_A_ID
        assert encrypted is not None
        assert job is not None
        assert job.job_kind is OutboxJobKind.WEBHOOK_NORMALIZE

    asyncio.run(exercise())


def test_attach_provider_payload_missing_webhook_rolls_back(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        with pytest.raises(AtomicContentCommandUnavailableError):
            await service.attach_provider_payload(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_A_ID,
                webhook_event_id=uuid4(),
                outbox_job_id=OUTBOX_JOB_ID,
                audit_event_id=AUDIT_EVENT_ID,
                plaintext=SYNTHETIC_PLAINTEXT_JSON,
                encoding=ContentEncoding.JSON,
                created_at=NOW,
                occurred_at=NOW,
                audit_context=_audit_context(),
                actor_type=AuditActorType.SERVICE,
                actor_id=SERVICE_ID,
            )
        lookup = integrated_uow_factory()
        async with lookup:
            encrypted = await lookup.encrypted_contents.get_by_id(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_A_ID,
            )
        assert encrypted is None

    asyncio.run(exercise())


def test_store_raw_message_writes_audit_event(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        await service.store_raw_message(
            tenant_id=TENANT_A_ID,
            content_id=CONTENT_A_ID,
            message_id=MESSAGE_B_ID,
            outbox_job_id=OUTBOX_JOB_B_ID,
            audit_event_id=AUDIT_EVENT_ID,
            conversation_thread_id=THREAD_A_ID,
            external_message_id="msg-atomic-audit",
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            sent_at=NOW,
            received_at=NOW,
            reply_to_message_id=None,
            adapter_metadata=synthetic_adapter_metadata(),
            plaintext=SYNTHETIC_PLAINTEXT_UTF8,
            created_at=NOW,
            occurred_at=NOW,
            audit_context=_audit_context(),
            actor_type=AuditActorType.SERVICE,
            actor_id=SERVICE_ID,
        )
        uow = integrated_uow_factory()
        async with uow:
            page = await uow.audit_events.query_page(
                query_filter=AuditQueryFilter(
                    tenant_id=TENANT_A_ID,
                    action=AuditAction.ENCRYPTED_CONTENT_STORED,
                ),
                cursor=None,
                page_size=10,
            )
        assert any(event.id == AUDIT_EVENT_ID for event in page.events)

    asyncio.run(exercise())


def test_store_raw_message_rejects_duplicate_outbox(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        service = _build_service(integrated_uow_factory)
        await service.store_raw_message(
            tenant_id=TENANT_A_ID,
            content_id=CONTENT_A_ID,
            message_id=MESSAGE_A_ID,
            outbox_job_id=OUTBOX_JOB_ID,
            audit_event_id=AUDIT_EVENT_ID,
            conversation_thread_id=THREAD_A_ID,
            external_message_id="msg-atomic-outbox-dup",
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            sent_at=NOW,
            received_at=NOW,
            reply_to_message_id=None,
            adapter_metadata=synthetic_adapter_metadata(),
            plaintext=SYNTHETIC_PLAINTEXT_UTF8,
            created_at=NOW,
            occurred_at=NOW,
            audit_context=_audit_context(),
            actor_type=AuditActorType.SERVICE,
            actor_id=SERVICE_ID,
        )
        with pytest.raises(AtomicContentCommandUnavailableError):
            await service.store_raw_message(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_B_ID,
                message_id=MESSAGE_B_ID,
                outbox_job_id=OUTBOX_JOB_ID,
                audit_event_id=uuid4(),
                conversation_thread_id=THREAD_A_ID,
                external_message_id="msg-atomic-outbox-dup-2",
                sender_type=ParticipantSenderType.CUSTOMER,
                direction=MessageDirection.INBOUND,
                sent_at=NOW,
                received_at=NOW,
                reply_to_message_id=None,
                adapter_metadata=synthetic_adapter_metadata(),
                plaintext=SYNTHETIC_PLAINTEXT_UTF8,
                created_at=NOW,
                occurred_at=NOW,
                audit_context=_audit_context(),
                actor_type=AuditActorType.SERVICE,
                actor_id=SERVICE_ID,
            )

    asyncio.run(exercise())
