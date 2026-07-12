"""Meta WhatsApp webhook GET verification service."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass

from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.provider_ports import WhatsAppCredentialResolver
from closeros.domain.whatsapp_cloud_connection import WhatsAppCloudConnectionStatus

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]

WEBHOOK_VERIFICATION_DENIED = "request denied"


class WhatsAppWebhookVerificationError(Exception):
    """Raised when webhook verification must be denied generically."""


@dataclass(frozen=True, slots=True)
class WhatsAppWebhookVerificationService:
    uow_factory: _UnitOfWorkFactory
    credential_resolver: WhatsAppCredentialResolver

    async def verify_subscription(
        self,
        *,
        webhook_public_key: str,
        hub_mode: str | None,
        hub_verify_token: str | None,
        hub_challenge: str | None,
    ) -> str:
        if hub_mode != "subscribe":
            raise WhatsAppWebhookVerificationError(WEBHOOK_VERIFICATION_DENIED)
        if not hub_verify_token or not hub_challenge:
            raise WhatsAppWebhookVerificationError(WEBHOOK_VERIFICATION_DENIED)

        uow = self.uow_factory()
        async with uow:
            record = await uow.whatsapp_cloud_connections.get_by_webhook_public_key(
                webhook_public_key=webhook_public_key,
            )
            if record is None:
                raise WhatsAppWebhookVerificationError(WEBHOOK_VERIFICATION_DENIED)
            if record.status not in (
                WhatsAppCloudConnectionStatus.ACTIVE.value,
                WhatsAppCloudConnectionStatus.VERIFICATION_PENDING.value,
            ):
                raise WhatsAppWebhookVerificationError(WEBHOOK_VERIFICATION_DENIED)
            if record.verify_token_ref is None:
                raise WhatsAppWebhookVerificationError(WEBHOOK_VERIFICATION_DENIED)
            expected = await self.credential_resolver.resolve_verify_token(
                tenant_id=record.tenant_id,
                whatsapp_connection_id=record.id,
                reference_key=record.verify_token_ref,
            )
            if expected is None:
                raise WhatsAppWebhookVerificationError(WEBHOOK_VERIFICATION_DENIED)
            if not hmac.compare_digest(hub_verify_token, expected.value.decode("utf-8")):
                raise WhatsAppWebhookVerificationError(WEBHOOK_VERIFICATION_DENIED)

        return hub_challenge
