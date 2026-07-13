"""Tests for notification delivery domain and adapters."""

# mypy: ignore-errors

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from closeros.application.audit_recording import AuditContext
from closeros.application.notification_delivery_service import (
    NotificationDeliveryService,
    recipient_hash,
)
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    DecryptedContent,
    EncryptedContentKind,
)
from closeros.domain.notification import (
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationKind,
    NotificationTemplateCode,
    render_email_verification_template,
)
from closeros.domain.notification_payload import NotificationPayload
from closeros.infrastructure.capture_notification_adapter import CaptureNotificationSender

NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
SERVICE_ACTOR_ID = uuid4()


def test_recipient_hash_is_stable_and_non_reversible() -> None:
    digest = recipient_hash(recipient="User@Example.com")
    assert digest == recipient_hash(recipient="user@example.com")
    assert "user@example.com" not in digest


def test_render_email_verification_template() -> None:
    template = render_email_verification_template(verification_url="https://app.example/verify")
    assert "Verify your CloserOS email address" in template.subject
    assert "https://app.example/verify" in template.body


def test_notification_delivery_validates_recipient_hash() -> None:
    with pytest.raises(ValueError):
        NotificationDelivery(
            id=uuid4(),
            tenant_id=None,
            payload_tenant_id=uuid4(),
            kind=NotificationKind.EMAIL_VERIFICATION,
            status=NotificationDeliveryStatus.PENDING,
            template_code=NotificationTemplateCode.EMAIL_VERIFICATION_V1.value,
            template_version=1,
            recipient_hash="not-a-hash",
            encrypted_payload_content_id=uuid4(),
            idempotency_key="notification_test",
            attempt_count=0,
            correlation_id=None,
            created_at=NOW,
            updated_at=NOW,
        )


def test_notification_payload_repr_hides_content() -> None:
    payload = NotificationPayload(
        recipient="user@example.com",
        subject="Secret subject",
        body="Secret body with token=abc",
    )
    rendered = repr(payload)
    assert "user@example.com" not in rendered
    assert "Secret" not in rendered
    assert "abc" not in rendered


def test_capture_notification_sender_records_email() -> None:
    async def exercise() -> None:
        sender = CaptureNotificationSender()
        await sender.send_email(
            recipient="user@example.com",
            subject="Hello",
            body="World",
        )
        assert len(sender.sent) == 1
        assert sender.sent[0].recipient == "user@example.com"

    asyncio.run(exercise())


def test_notification_delivery_service_deliver_pending_decrypts_payload() -> None:
    async def exercise() -> None:
        delivery_id = uuid4()
        payload_content_id = uuid4()
        sender = CaptureNotificationSender()
        payload = NotificationPayload(
            recipient="user@example.com",
            subject="Verify",
            body="Click https://app.example/verify?token=safe",
        )

        class _Deliveries:
            async def get_by_id(self, *, tenant_id, delivery_id):  # type: ignore[no-untyped-def]
                return NotificationDelivery(
                    id=delivery_id,
                    tenant_id=tenant_id,
                    payload_tenant_id=uuid4(),
                    kind=NotificationKind.EMAIL_VERIFICATION,
                    status=NotificationDeliveryStatus.PENDING,
                    template_code=NotificationTemplateCode.EMAIL_VERIFICATION_V1.value,
                    template_version=1,
                    recipient_hash=recipient_hash(recipient="user@example.com"),
                    encrypted_payload_content_id=payload_content_id,
                    idempotency_key="notification_test",
                    attempt_count=0,
                    correlation_id=None,
                    created_at=NOW,
                    updated_at=NOW,
                )

            async def update_status(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
                return None

        class _Attempts:
            async def add(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
                return None

        class _EncryptedContents:
            async def delete(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
                return None

        class _ContentEncryption:
            async def load_and_decrypt(self, **kwargs):  # type: ignore[no-untyped-def]
                assert kwargs["purpose"] is ContentAccessPurpose.NOTIFICATION_DELIVERY
                plaintext = payload.to_json_bytes()
                return DecryptedContent(
                    kind=EncryptedContentKind.NOTIFICATION_PAYLOAD,
                    encoding=ContentEncoding.JSON,
                    plaintext_byte_length=len(plaintext),
                    _plaintext=plaintext,
                )

        class _Uow:
            notification_deliveries = _Deliveries()
            notification_delivery_attempts = _Attempts()
            encrypted_contents = _EncryptedContents()

            async def __aenter__(self):  # type: ignore[no-untyped-def]
                return self

            async def __aexit__(self, *args) -> None:  # type: ignore[no-untyped-def]
                return None

            async def commit(self) -> None:
                return None

        service = NotificationDeliveryService(
            uow_factory=lambda: _Uow(),
            uuid_factory=uuid4,
            content_encryption=_ContentEncryption(),
            verification_base_url="https://app.example/verify",
            reset_base_url="https://app.example/reset",
            service_actor_id=SERVICE_ACTOR_ID,
        )
        await service.deliver_pending(
            tenant_id=None,
            delivery_id=delivery_id,
            sender=sender,
            occurred_at=NOW,
            audit_context=AuditContext(correlation_id=uuid4()),
        )
        assert sender.sent[0].subject == "Verify"
        assert "safe" in sender.sent[0].body

    asyncio.run(exercise())


def test_notification_delivery_rejects_half_linked_payload_reference() -> None:
    with pytest.raises(ValueError, match="fully linked or fully cleared"):
        NotificationDelivery(
            id=uuid4(),
            tenant_id=uuid4(),
            payload_tenant_id=uuid4(),
            kind=NotificationKind.EMAIL_VERIFICATION,
            status=NotificationDeliveryStatus.PENDING,
            template_code=NotificationTemplateCode.EMAIL_VERIFICATION_V1.value,
            template_version=1,
            recipient_hash=recipient_hash(recipient="user@example.com"),
            encrypted_payload_content_id=None,
            idempotency_key="notification_test",
            attempt_count=0,
            correlation_id=None,
            created_at=NOW,
            updated_at=NOW,
        )


@pytest.mark.hi_persistence
def test_successful_notification_delivery_deletes_payload_without_fk_error(
    integrated_uow_factory: Any,
    auth_async_engine: Any,
) -> None:
    from closeros.application.notification_deliver_handler import NotificationDeliverHandler
    from closeros.domain.outbox import OutboxJobKind, OutboxJobReference, build_outbox_job
    from closeros.infrastructure.capture_notification_adapter import CaptureNotificationSender
    from sqlalchemy import text

    from tests.encryption_support import build_content_encryption_service
    from tests.tenant_persistence_support import TENANT_A_ID, synthetic_tenant

    async def exercise() -> None:
        uow = integrated_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant(tenant_id=TENANT_A_ID))
            await uow.commit()

        delivery_id = uuid4()
        payload_content_id = uuid4()
        job_id = uuid4()
        payload = NotificationPayload(
            recipient="notify.test@example.test",
            subject="Verify",
            body="Click https://app.example/verify?token=safe",
        )
        content_encryption = build_content_encryption_service(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            await content_encryption.encrypt_and_persist(
                uow,
                content_id=payload_content_id,
                tenant_id=TENANT_A_ID,
                kind=EncryptedContentKind.NOTIFICATION_PAYLOAD,
                encoding=ContentEncoding.JSON,
                plaintext=payload.to_json_bytes(),
                created_at=NOW,
            )
            await uow.notification_deliveries.add(
                delivery=NotificationDelivery(
                    id=delivery_id,
                    tenant_id=TENANT_A_ID,
                    payload_tenant_id=TENANT_A_ID,
                    kind=NotificationKind.EMAIL_VERIFICATION,
                    status=NotificationDeliveryStatus.PENDING,
                    template_code=NotificationTemplateCode.EMAIL_VERIFICATION_V1.value,
                    template_version=1,
                    recipient_hash=recipient_hash(recipient=payload.recipient),
                    encrypted_payload_content_id=payload_content_id,
                    idempotency_key=f"notification_{delivery_id}",
                    attempt_count=0,
                    correlation_id=job_id,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await uow.outbox_jobs.enqueue(
                build_outbox_job(
                    job_id=job_id,
                    tenant_id=TENANT_A_ID,
                    job_kind=OutboxJobKind.NOTIFICATION_DELIVER,
                    reference=OutboxJobReference(
                        resource_type="notification_delivery",
                        resource_id=delivery_id,
                        schema_version=1,
                        tenant_id=TENANT_A_ID,
                    ),
                    deduplication_key=f"notification_{delivery_id}",
                    created_at=NOW,
                )
            )
            await uow.commit()

        sender = CaptureNotificationSender()
        delivery_service = NotificationDeliveryService(
            uow_factory=integrated_uow_factory,
            uuid_factory=uuid4,
            content_encryption=content_encryption,
            verification_base_url="https://app.example/verify",
            reset_base_url="https://app.example/reset",
            service_actor_id=SERVICE_ACTOR_ID,
        )
        handler = NotificationDeliverHandler(
            uow_factory=integrated_uow_factory,
            delivery_service=delivery_service,
            sender=sender,
            service_actor_id=SERVICE_ACTOR_ID,
        )
        job = build_outbox_job(
            job_id=job_id,
            tenant_id=TENANT_A_ID,
            job_kind=OutboxJobKind.NOTIFICATION_DELIVER,
            reference=OutboxJobReference(
                resource_type="notification_delivery",
                resource_id=delivery_id,
                schema_version=1,
                tenant_id=TENANT_A_ID,
            ),
            deduplication_key=f"notification_{delivery_id}",
            created_at=NOW,
        )
        await handler.handle(job=job)
        assert len(sender.sent) == 1

        async with auth_async_engine.connect() as connection:
            delivery_row = (
                await connection.execute(
                    text(
                        """
                        SELECT tenant_id, payload_tenant_id, encrypted_payload_content_id,
                               status, template_code
                        FROM notification_deliveries
                        WHERE id = :delivery_id
                        """
                    ),
                    {"delivery_id": delivery_id},
                )
            ).one()
            encrypted_count = (
                await connection.execute(
                    text("SELECT COUNT(*) FROM encrypted_contents WHERE id = :content_id"),
                    {"content_id": payload_content_id},
                )
            ).scalar_one()

        assert delivery_row.status == "succeeded"
        assert delivery_row.tenant_id == TENANT_A_ID
        assert delivery_row.payload_tenant_id is None
        assert delivery_row.encrypted_payload_content_id is None
        assert delivery_row.template_code == NotificationTemplateCode.EMAIL_VERIFICATION_V1.value
        assert encrypted_count == 0

        await handler.handle(job=job)
        assert len(sender.sent) == 1

    asyncio.run(exercise())
