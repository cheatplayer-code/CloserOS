"""Atomic authentication notification issuance inside a single unit of work."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.application.authentication_notification_delivery import (
    AuthenticationNotificationDelivery,
)
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.notification_delivery_service import recipient_hash
from closeros.application.outbox_persistence import DuplicateOutboxJobError
from closeros.domain.authentication import AuthenticationTokenPurpose
from closeros.domain.encrypted_content import ContentEncoding, EncryptedContentKind
from closeros.domain.notification import (
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

_UuidFactory = Callable[[], UUID]
PLATFORM_NOTIFICATION_TENANT_ID = UUID(PLATFORM_NOTIFICATION_TENANT_ID_STR)


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


@dataclass(frozen=True, slots=True)
class AtomicAuthenticationNotificationIssuer:
    """Persists encrypted notification payloads and outbox jobs without committing."""

    content_encryption: ContentEncryptionService
    uuid_factory: _UuidFactory
    verification_base_url: str
    reset_base_url: str

    async def enqueue_in_transaction(
        self,
        uow: IntegratedUnitOfWork,
        *,
        delivery: AuthenticationNotificationDelivery,
        purpose: AuthenticationTokenPurpose,
        tenant_id: UUID | None,
        requested_at: datetime,
    ) -> UUID:
        delivery_id = self.uuid_factory()
        job_id = self.uuid_factory()
        payload_content_id = self.uuid_factory()
        kind = _kind_for_auth_purpose(purpose)
        template_code, template_version = _template_for_kind(kind)
        token = delivery.raw_token.value
        recipient = delivery.recipient.value

        if kind is NotificationKind.EMAIL_VERIFICATION:
            template = render_email_verification_template(
                verification_url=f"{self.verification_base_url}?token={token}",
            )
        else:
            template = render_password_reset_template(
                reset_url=f"{self.reset_base_url}?token={token}",
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
            tenant_id=tenant_id if tenant_id is not None else payload_tenant_id,
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

        await self.content_encryption.encrypt_and_persist(
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
                    tenant_id=payload_tenant_id,
                    job_kind=OutboxJobKind.NOTIFICATION_DELIVER,
                    reference=OutboxJobReference(
                        resource_type="notification_delivery",
                        resource_id=delivery_id,
                        schema_version=1,
                        tenant_id=payload_tenant_id,
                    ),
                    deduplication_key=idempotency_key,
                    created_at=requested_at,
                )
            )
        return delivery_id


__all__ = ["AtomicAuthenticationNotificationIssuer"]
