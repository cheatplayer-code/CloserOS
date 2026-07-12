"""PostgreSQL integration tests for content redaction outbox handler."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from closeros.application.audit_persistence import AuditQueryFilter
from closeros.application.audit_recording import AuditContext
from closeros.application.content_redact_handler import ContentRedactHandler
from closeros.application.metrics_enqueue_service import MetricsEnqueueService
from closeros.domain.audit import AuditAction, AuditActorType
from closeros.domain.content_sanitization import default_policy_version
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    EncryptedContentKind,
)
from closeros.domain.outbox import OutboxJob, OutboxJobKind, OutboxJobReference, build_outbox_job
from closeros.domain.privacy_redaction import AnalysisEligibility

from tests.auth_api_support import SequenceUuidFactory
from tests.canonical_persistence_support import (
    CONTENT_A_ID,
    CONTENT_B_ID,
    EDIT_EVENT_A_ID,
    MESSAGE_A_ID,
    NOW,
    SALES_CASE_A_ID,
    synthetic_channel_connection,
    synthetic_conversation_thread,
    synthetic_message,
    synthetic_message_edit_event,
    synthetic_sales_case,
)
from tests.encryption_support import (
    OUTBOX_JOB_ID,
    SERVICE_ID,
    build_content_encryption_service,
)
from tests.tenant_persistence_support import TENANT_A_ID, TENANT_B_ID, synthetic_tenant

pytestmark = pytest.mark.lm_persistence

CORRELATION_ID = UUID("00000000-0000-0000-0000-000000000999")
SANITIZATION_ID = UUID("00000000-0000-0000-0000-000000000f01")
SANITIZED_CONTENT_ID = UUID("00000000-0000-0000-0000-000000000f02")

SYNTHETIC_EMAIL_PLAINTEXT = b"Synthetic inquiry from synthetic.redact@example.test about pricing."
SYNTHETIC_CONTROL_PLAINTEXT = b"Blocked synthetic payload\x00with control bytes."
SYNTHETIC_CLEAN_PLAINTEXT = b"Synthetic message without sensitive identifiers."


def _audit_context() -> AuditContext:
    return AuditContext(correlation_id=CORRELATION_ID)


def _uuid_factory() -> SequenceUuidFactory:
    return SequenceUuidFactory(
        [
            SANITIZATION_ID,
            SANITIZED_CONTENT_ID,
            UUID("00000000-0000-0000-0000-000000000f04"),
            UUID("00000000-0000-0000-0000-000000000f05"),
            UUID("00000000-0000-0000-0000-000000000f06"),
            UUID("00000000-0000-0000-0000-000000000f07"),
        ]
    )


def _build_handler(integrated_uow_factory: Any) -> ContentRedactHandler:
    return ContentRedactHandler(
        uow_factory=integrated_uow_factory,
        content_encryption=build_content_encryption_service(integrated_uow_factory),
        metrics_enqueue=MetricsEnqueueService(
            uow_factory=integrated_uow_factory,
            uuid_factory=uuid4,
            service_actor_id=SERVICE_ID,
        ),
        service_actor_id=SERVICE_ID,
        uuid_factory=_uuid_factory(),
    )


def _redact_job(
    *,
    resource_type: str,
    resource_id: UUID,
    content_id: UUID,
    job_id: UUID = OUTBOX_JOB_ID,
    deduplication_key: str = "content_redact_message_test",
) -> OutboxJob:
    return build_outbox_job(
        job_id=job_id,
        tenant_id=TENANT_A_ID,
        job_kind=OutboxJobKind.CONTENT_REDACT,
        reference=OutboxJobReference(
            tenant_id=TENANT_A_ID,
            resource_type=resource_type,
            resource_id=resource_id,
            secondary_id=content_id,
            schema_version=1,
        ),
        deduplication_key=deduplication_key,
        created_at=NOW,
    )


async def _seed_platform_graph(integrated_uow_factory: Any) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant())
        await uow.tenants.add(
            synthetic_tenant(
                tenant_id=TENANT_B_ID,
                name="Synthetic Tenant B",
            )
        )
        await uow.channel_connections.add(synthetic_channel_connection())
        await uow.sales_cases.add(synthetic_sales_case())
        await uow.conversation_threads.add(
            synthetic_conversation_thread(sales_case_id=SALES_CASE_A_ID, lifecycle_status=None)
        )
        await uow.commit()


async def _append_message_with_content(integrated_uow_factory: Any) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.messages.append(synthetic_message(content_id=CONTENT_A_ID))
        await uow.commit()


async def _append_edit_with_content(integrated_uow_factory: Any) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.messages.append(synthetic_message(content_id=None))
        await uow.message_edit_events.append(synthetic_message_edit_event(content_id=CONTENT_B_ID))
        await uow.commit()


async def _persist_raw_content(
    integrated_uow_factory: Any,
    *,
    content_id: UUID,
    plaintext: bytes,
    encoding: ContentEncoding = ContentEncoding.UTF8,
) -> None:
    service = build_content_encryption_service(integrated_uow_factory)
    uow = integrated_uow_factory()
    async with uow:
        await service.encrypt_and_persist(
            uow,
            content_id=content_id,
            tenant_id=TENANT_A_ID,
            kind=EncryptedContentKind.RAW_MESSAGE,
            encoding=encoding,
            plaintext=plaintext,
            created_at=NOW,
        )
        await uow.commit()


def test_content_redact_handler_sanitizes_message_reference(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        await _persist_raw_content(
            integrated_uow_factory,
            content_id=CONTENT_A_ID,
            plaintext=SYNTHETIC_EMAIL_PLAINTEXT,
        )
        await _append_message_with_content(integrated_uow_factory)
        handler = _build_handler(integrated_uow_factory)
        await handler.handle(
            job=_redact_job(
                resource_type="message",
                resource_id=MESSAGE_A_ID,
                content_id=CONTENT_A_ID,
            )
        )
        uow = integrated_uow_factory()
        async with uow:
            record = await uow.content_sanitizations.get_completed_by_source(
                tenant_id=TENANT_A_ID,
                source_content_id=CONTENT_A_ID,
                policy_version=default_policy_version(),
            )
        assert record is not None
        assert record.source_resource_type == "message"
        assert record.source_resource_id == MESSAGE_A_ID
        assert record.analysis_eligibility is AnalysisEligibility.ELIGIBLE
        assert record.sanitized_content_id == SANITIZED_CONTENT_ID
        assert record.total_finding_count == 1
        assert len(record.category_counts) == 1
        assert record.category_counts[0].category == "email"
        assert record.category_counts[0].count == 1

    asyncio.run(exercise())


def test_content_redact_handler_sanitizes_message_edit_reference(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        await _persist_raw_content(
            integrated_uow_factory,
            content_id=CONTENT_B_ID,
            plaintext=SYNTHETIC_CLEAN_PLAINTEXT,
        )
        await _append_edit_with_content(integrated_uow_factory)
        handler = _build_handler(integrated_uow_factory)
        await handler.handle(
            job=_redact_job(
                resource_type="message_edit_event",
                resource_id=EDIT_EVENT_A_ID,
                content_id=CONTENT_B_ID,
                deduplication_key="content_redact_edit_test",
            )
        )
        uow = integrated_uow_factory()
        async with uow:
            record = await uow.content_sanitizations.get_completed_by_source(
                tenant_id=TENANT_A_ID,
                source_content_id=CONTENT_B_ID,
                policy_version=default_policy_version(),
            )
        assert record is not None
        assert record.source_resource_type == "message_edit_event"
        assert record.source_resource_id == EDIT_EVENT_A_ID
        assert record.analysis_eligibility is AnalysisEligibility.NOT_APPLICABLE
        assert record.sanitized_content_id is None
        assert record.total_finding_count == 0

    asyncio.run(exercise())


def test_content_redact_handler_is_idempotent(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        await _persist_raw_content(
            integrated_uow_factory,
            content_id=CONTENT_A_ID,
            plaintext=SYNTHETIC_CLEAN_PLAINTEXT,
        )
        await _append_message_with_content(integrated_uow_factory)
        handler = _build_handler(integrated_uow_factory)
        job = _redact_job(
            resource_type="message",
            resource_id=MESSAGE_A_ID,
            content_id=CONTENT_A_ID,
            deduplication_key="content_redact_idempotent_test",
        )
        await handler.handle(job=job)
        await handler.handle(job=job)
        uow = integrated_uow_factory()
        async with uow:
            record = await uow.content_sanitizations.get_completed_by_source(
                tenant_id=TENANT_A_ID,
                source_content_id=CONTENT_A_ID,
                policy_version=default_policy_version(),
            )
        assert record is not None

    asyncio.run(exercise())


def test_content_redact_handler_blocks_control_content(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        await _persist_raw_content(
            integrated_uow_factory,
            content_id=CONTENT_A_ID,
            plaintext=SYNTHETIC_CONTROL_PLAINTEXT,
        )
        await _append_message_with_content(integrated_uow_factory)
        handler = _build_handler(integrated_uow_factory)
        await handler.handle(
            job=_redact_job(
                resource_type="message",
                resource_id=MESSAGE_A_ID,
                content_id=CONTENT_A_ID,
                deduplication_key="content_redact_blocked_test",
            )
        )
        uow = integrated_uow_factory()
        async with uow:
            record = await uow.content_sanitizations.get_completed_by_source(
                tenant_id=TENANT_A_ID,
                source_content_id=CONTENT_A_ID,
                policy_version=default_policy_version(),
            )
            page = await uow.audit_events.query_page(
                query_filter=AuditQueryFilter(tenant_id=TENANT_A_ID),
                cursor=None,
                page_size=20,
            )
        assert record is not None
        assert record.analysis_eligibility is AnalysisEligibility.BLOCKED
        assert record.sanitized_content_id is None
        assert any(
            event.action is AuditAction.CONTENT_SANITIZATION_BLOCKED for event in page.events
        )

    asyncio.run(exercise())


def test_content_redact_handler_persists_encrypted_sanitized_output(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        await _persist_raw_content(
            integrated_uow_factory,
            content_id=CONTENT_A_ID,
            plaintext=SYNTHETIC_EMAIL_PLAINTEXT,
        )
        await _append_message_with_content(integrated_uow_factory)
        handler = _build_handler(integrated_uow_factory)
        await handler.handle(
            job=_redact_job(
                resource_type="message",
                resource_id=MESSAGE_A_ID,
                content_id=CONTENT_A_ID,
                deduplication_key="content_redact_encrypted_output_test",
            )
        )
        service = build_content_encryption_service(integrated_uow_factory)
        decrypted = await service.load_and_decrypt(
            tenant_id=TENANT_A_ID,
            content_id=SANITIZED_CONTENT_ID,
            purpose=ContentAccessPurpose.AI_ANALYSIS,
            occurred_at=NOW,
            audit_context=_audit_context(),
            actor_type=AuditActorType.SERVICE,
            actor_id=SERVICE_ID,
            audit_event_id=UUID("00000000-0000-0000-0000-000000000f08"),
        )
        assert decrypted.kind is EncryptedContentKind.SANITIZED_MESSAGE
        sanitized_bytes = decrypted.as_bytes()
        assert b"synthetic.redact@example.test" not in sanitized_bytes
        assert b"[REDACTED_EMAIL]" in sanitized_bytes

    asyncio.run(exercise())


def test_content_redact_handler_blocks_unsupported_encoding(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        await _persist_raw_content(
            integrated_uow_factory,
            content_id=CONTENT_A_ID,
            plaintext=b'{"synthetic": true}',
            encoding=ContentEncoding.JSON,
        )
        await _append_message_with_content(integrated_uow_factory)
        handler = _build_handler(integrated_uow_factory)
        await handler.handle(
            job=_redact_job(
                resource_type="message",
                resource_id=MESSAGE_A_ID,
                content_id=CONTENT_A_ID,
                deduplication_key="content_redact_encoding_test",
            )
        )
        uow = integrated_uow_factory()
        async with uow:
            record = await uow.content_sanitizations.get_completed_by_source(
                tenant_id=TENANT_A_ID,
                source_content_id=CONTENT_A_ID,
                policy_version=default_policy_version(),
            )
        assert record is not None
        assert record.analysis_eligibility is AnalysisEligibility.BLOCKED
        assert record.sanitized_content_id is None

    asyncio.run(exercise())


def test_content_redact_handler_enforces_tenant_isolation(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_graph(integrated_uow_factory)
        await _persist_raw_content(
            integrated_uow_factory,
            content_id=CONTENT_A_ID,
            plaintext=SYNTHETIC_CLEAN_PLAINTEXT,
        )
        await _append_message_with_content(integrated_uow_factory)
        handler = _build_handler(integrated_uow_factory)
        await handler.handle(
            job=_redact_job(
                resource_type="message",
                resource_id=MESSAGE_A_ID,
                content_id=CONTENT_A_ID,
                deduplication_key="content_redact_tenant_isolation_test",
            )
        )
        uow = integrated_uow_factory()
        async with uow:
            tenant_a_record = await uow.content_sanitizations.get_completed_by_source(
                tenant_id=TENANT_A_ID,
                source_content_id=CONTENT_A_ID,
                policy_version=default_policy_version(),
            )
            tenant_b_record = await uow.content_sanitizations.get_completed_by_source(
                tenant_id=TENANT_B_ID,
                source_content_id=CONTENT_A_ID,
                policy_version=default_policy_version(),
            )
        assert tenant_a_record is not None
        assert tenant_b_record is None

    asyncio.run(exercise())
