"""Notification delivery orchestration with encrypted payloads."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext
from closeros.application.authentication_notification_delivery import (
    AuthenticationNotificationDelivery,
)
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.notification_ports import (
    NotificationDeliveryAttemptRecord,
    NotificationDeliveryNotFoundError,
    NotificationSender,
    NotificationSenderError,
    NotificationSenderTransientError,
)
from closeros.application.outbox_persistence import DuplicateOutboxJobError
from closeros.domain.audit import AuditActorType
from closeros.domain.authentication import AuthenticationTokenPurpose
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    EncryptedContentKind,
)
from closeros.domain.notification import (
    NotificationAttemptOutcome,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationKind,
    NotificationTemplateCode,
    render_email_verification_template,
    render_password_reset_template,
)
from closeros.domain.notification_payload import (
    PLATFORM_NOTIFICATION_TENANT_ID_STR,
    NotificationPayload,
)
from closeros.domain.outbox import OutboxJobKind, OutboxJobReference, build_outbox_job

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
PLATFORM_NOTIFICATION_TENANT_ID = UUID(PLATFORM_NOTIFICATION_TENANT_ID_STR)


def recipient_hash(*, recipient: str) -> str:
    normalized = recipient.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _kind_for_auth_purpose(purpose: AuthenticationTokenPurpose) -> NotificationKind:
    if purpose is AuthenticationTokenPurpose.EMAIL_VERIFICATION:
        return NotificationKind.EMAIL_VERIFICATION
    if purpose is AuthenticationTokenPurpose.PASSWORD_RESET:
        return NotificationKind.PASSWORD_RESET
    raise ValueError("unsupported authentication notification purpose")


def _template_for_kind(kind: NotificationKind) -> tuple[str, int]:
    if kind is NotificationKind.EMAIL_VERIFICATION:
        return NotificationTemplateCode.EMAIL_VERIFICATION_V1.value, 1
    if kind is NotificationKind.PASSWORD_RESET:
        return NotificationTemplateCode.PASSWORD_RESET_V1.value, 1
    raise ValueError("unsupported notification kind")


def _payload_tenant_id(*, tenant_id: UUID | None) -> UUID:
    return tenant_id if tenant_id is not None else PLATFORM_NOTIFICATION_TENANT_ID


class NotificationDeliveryUnavailableError(Exception):
    """Raised when notification delivery cannot be enqueued or completed."""


class NotificationDeliveryService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        uuid_factory: _UuidFactory,
        content_encryption: ContentEncryptionService,
        verification_base_url: str,
        reset_base_url: str,
        service_actor_id: UUID,
    ) -> None:
        self._uow_factory = uow_factory
        self._uuid_factory = uuid_factory
        self._content_encryption = content_encryption
        self._verification_base_url = verification_base_url.rstrip("/")
        self._reset_base_url = reset_base_url.rstrip("/")
        self._service_actor_id = service_actor_id

    async def enqueue_authentication_notification(
        self,
        *,
        delivery: AuthenticationNotificationDelivery,
        purpose: AuthenticationTokenPurpose,
        tenant_id: UUID | None,
        requested_at: datetime,
    ) -> UUID:
        delivery_id = self._uuid_factory()
        job_id = self._uuid_factory()
        payload_content_id = self._uuid_factory()
        kind = _kind_for_auth_purpose(purpose)
        template_code, template_version = _template_for_kind(kind)
        token = delivery.raw_token.value
        recipient = delivery.recipient.value

        if kind is NotificationKind.EMAIL_VERIFICATION:
            template = render_email_verification_template(
                verification_url=f"{self._verification_base_url}?token={token}",
            )
        else:
            template = render_password_reset_template(
                reset_url=f"{self._reset_base_url}?token={token}",
            )

        payload = NotificationPayload(
            recipient=recipient,
            subject=template.subject,
            body=template.body,
        )
        payload_tenant_id = _payload_tenant_id(tenant_id=tenant_id)
        idempotency_key = f"notification_{delivery_id}"

        notification = NotificationDelivery(
            id=delivery_id,
            tenant_id=tenant_id,
            payload_tenant_id=payload_tenant_id,
            kind=kind,
            status=NotificationDeliveryStatus.PENDING,
            template_code=template_code,
            template_version=template_version,
            recipient_hash=recipient_hash(recipient=recipient),
            encrypted_payload_content_id=payload_content_id,
            idempotency_key=idempotency_key,
            attempt_count=0,
            correlation_id=job_id,
            created_at=requested_at,
            updated_at=requested_at,
        )

        uow = self._uow_factory()
        async with uow:
            await self._content_encryption.encrypt_and_persist(
                uow,
                content_id=payload_content_id,
                tenant_id=payload_tenant_id,
                kind=EncryptedContentKind.NOTIFICATION_PAYLOAD,
                encoding=ContentEncoding.JSON,
                plaintext=payload.to_json_bytes(),
                created_at=requested_at,
            )
            await uow.notification_deliveries.add(delivery=notification)
            with suppress(DuplicateOutboxJobError):
                await uow.outbox_jobs.enqueue(
                    build_outbox_job(
                        job_id=job_id,
                        tenant_id=tenant_id,
                        job_kind=OutboxJobKind.NOTIFICATION_DELIVER,
                        reference=OutboxJobReference(
                            resource_type="notification_delivery",
                            resource_id=delivery_id,
                            schema_version=1,
                            tenant_id=tenant_id,
                        ),
                        deduplication_key=idempotency_key,
                        created_at=requested_at,
                    )
                )
            await uow.commit()

        return delivery_id

    async def deliver_pending(
        self,
        *,
        tenant_id: UUID | None,
        delivery_id: UUID,
        sender: NotificationSender,
        occurred_at: datetime,
        audit_context: AuditContext,
    ) -> None:
        uow = self._uow_factory()
        async with uow:
            delivery = await uow.notification_deliveries.get_by_id(
                tenant_id=tenant_id,
                delivery_id=delivery_id,
            )
            if delivery is None:
                raise NotificationDeliveryNotFoundError("notification delivery not found")
            if delivery.status is NotificationDeliveryStatus.SUCCEEDED:
                return
            if delivery.encrypted_payload_content_id is None:
                raise NotificationDeliveryUnavailableError(
                    "notification payload is unavailable for delivery"
                )

            await uow.notification_deliveries.update_status(
                tenant_id=tenant_id,
                delivery_id=delivery_id,
                status=NotificationDeliveryStatus.DELIVERING,
                updated_at=occurred_at,
                attempt_count=delivery.attempt_count + 1,
            )
            await uow.commit()

        attempt_number = delivery.attempt_count + 1
        outcome = NotificationAttemptOutcome.TRANSIENT_FAILED
        error_code: str | None = "delivery_failed"
        final_status = NotificationDeliveryStatus.FAILED
        delivered_at: datetime | None = None
        payload_content_id = delivery.encrypted_payload_content_id
        assert payload_content_id is not None

        payload_tenant_id = delivery.payload_tenant_id
        assert payload_tenant_id is not None

        delivery_succeeded = False
        try:
            decrypted = await self._content_encryption.load_and_decrypt(
                tenant_id=payload_tenant_id,
                content_id=payload_content_id,
                purpose=ContentAccessPurpose.NOTIFICATION_DELIVERY,
                occurred_at=occurred_at,
                audit_context=audit_context,
                actor_type=AuditActorType.SERVICE,
                actor_id=self._service_actor_id,
                audit_event_id=self._uuid_factory(),
            )
            payload = NotificationPayload.from_json_bytes(decrypted.as_bytes())
            await sender.send_email(
                recipient=payload.recipient,
                subject=payload.subject,
                body=payload.body,
            )
            uow = self._uow_factory()
            async with uow:
                await uow.notification_delivery_attempts.add(
                    attempt=NotificationDeliveryAttemptRecord(
                        id=self._uuid_factory(),
                        tenant_id=tenant_id,
                        delivery_id=delivery_id,
                        attempt_number=attempt_number,
                        outcome=NotificationAttemptOutcome.SUCCEEDED,
                        error_code=None,
                        started_at=occurred_at,
                        finished_at=occurred_at,
                    )
                )
                await uow.encrypted_contents.delete(
                    tenant_id=payload_tenant_id,
                    content_id=payload_content_id,
                )
                await uow.notification_deliveries.update_status(
                    tenant_id=tenant_id,
                    delivery_id=delivery_id,
                    status=NotificationDeliveryStatus.SUCCEEDED,
                    updated_at=occurred_at,
                    delivered_at=occurred_at,
                    last_error_code=None,
                    attempt_count=attempt_number,
                )
                await uow.commit()
            delivery_succeeded = True
        except NotificationSenderTransientError:
            error_code = "smtp_transient_failure"
            final_status = NotificationDeliveryStatus.PENDING
            raise
        except NotificationSenderError:
            error_code = "smtp_permanent_failure"
            final_status = NotificationDeliveryStatus.FAILED
            raise
        except Exception:
            error_code = "delivery_failed"
            raise
        else:
            return
        finally:
            if not delivery_succeeded:
                uow = self._uow_factory()
                async with uow:
                    await uow.notification_delivery_attempts.add(
                        attempt=NotificationDeliveryAttemptRecord(
                            id=self._uuid_factory(),
                            tenant_id=tenant_id,
                            delivery_id=delivery_id,
                            attempt_number=attempt_number,
                            outcome=outcome,
                            error_code=error_code,
                            started_at=occurred_at,
                            finished_at=occurred_at,
                        )
                    )
                    await uow.notification_deliveries.update_status(
                        tenant_id=tenant_id,
                        delivery_id=delivery_id,
                        status=final_status,
                        updated_at=occurred_at,
                        delivered_at=delivered_at,
                        last_error_code=error_code,
                        attempt_count=attempt_number,
                    )
                    await uow.commit()


__all__ = [
    "NotificationDeliveryService",
    "NotificationDeliveryUnavailableError",
    "PLATFORM_NOTIFICATION_TENANT_ID",
    "recipient_hash",
]
