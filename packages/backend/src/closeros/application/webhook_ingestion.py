"""Webhook ingestion application service."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.application.atomic_content_commands import (
    AtomicContentCommandService,
    AtomicContentCommandUnavailableError,
)
from closeros.application.audit_recording import AuditContext
from closeros.application.ingestion_audit import provider_code_for_kind
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.provider_adapter_registry import (
    ProviderAdapterRegistry,
    UnknownProviderAdapterError,
)
from closeros.application.provider_ports import (
    ProviderSignatureError,
    WebhookRateLimiter,
)
from closeros.domain.audit import AuditActorType
from closeros.domain.canonical_enums import ChannelConnectionStatus, ProviderKind
from closeros.domain.encrypted_content import ContentEncoding

WEBHOOK_ACCEPTED_RESPONSE = "accepted"
WEBHOOK_DENIED_RESPONSE = "request denied"
WEBHOOK_MAX_BODY_BYTES = 1024 * 1024

_ACTIVE_CONNECTION_STATUSES = frozenset(
    {
        ChannelConnectionStatus.ACTIVE,
        ChannelConnectionStatus.DEGRADED,
    }
)


class WebhookIngestionError(Exception):
    """Base class for safe webhook ingestion failures."""


class WebhookIngestionDeniedError(WebhookIngestionError):
    """Raised when a webhook request must be denied generically."""


@dataclass(frozen=True, slots=True)
class WebhookAcceptanceResult:
    accepted: bool
    duplicate: bool


@dataclass(frozen=True, slots=True)
class WebhookIngestionService:
    uow_factory: Callable[[], IntegratedUnitOfWork]
    atomic_commands: AtomicContentCommandService
    adapter_registry: ProviderAdapterRegistry
    rate_limiter: WebhookRateLimiter
    service_actor_id: UUID
    uuid_factory: Callable[[], UUID]
    webhook_rate_limit: int = 120
    webhook_rate_window_seconds: int = 60

    async def accept_provider_webhook(
        self,
        *,
        provider_kind: ProviderKind,
        connection_id: UUID,
        raw_body: bytes,
        headers: Mapping[str, str],
        content_length: int | None,
        audit_context: AuditContext,
        received_at: datetime,
    ) -> WebhookAcceptanceResult:
        if content_length is not None and content_length > WEBHOOK_MAX_BODY_BYTES:
            raise WebhookIngestionDeniedError(WEBHOOK_DENIED_RESPONSE)

        if not raw_body or len(raw_body) > WEBHOOK_MAX_BODY_BYTES:
            raise WebhookIngestionDeniedError(WEBHOOK_DENIED_RESPONSE)

        allowed = await self.rate_limiter.check_webhook(
            scope_key=f"webhook:{provider_kind.value}",
            limit=self.webhook_rate_limit,
            window_seconds=self.webhook_rate_window_seconds,
        )
        if not allowed:
            raise WebhookIngestionDeniedError(WEBHOOK_DENIED_RESPONSE)

        try:
            adapter = self.adapter_registry.resolve(provider_kind)
        except UnknownProviderAdapterError as error:
            raise WebhookIngestionDeniedError(WEBHOOK_DENIED_RESPONSE) from error

        uow = self.uow_factory()
        async with uow:
            connection = await uow.channel_connections.get_by_connection_id(
                connection_id=connection_id,
            )
            if connection is None or connection.provider is not provider_kind:
                raise WebhookIngestionDeniedError(WEBHOOK_DENIED_RESPONSE)

            if connection.status not in _ACTIVE_CONNECTION_STATUSES:
                raise WebhookIngestionDeniedError(WEBHOOK_DENIED_RESPONSE)

            tenant_id = connection.tenant_id

        try:
            verified = await adapter.verify_webhook(
                raw_body=raw_body,
                headers=headers,
                connection_id=connection_id,
                tenant_id=tenant_id,
            )
        except ProviderSignatureError as error:
            raise WebhookIngestionDeniedError(WEBHOOK_DENIED_RESPONSE) from error

        encoding = _encoding_for_content_type(verified.received_content_type)

        try:
            result = await self.atomic_commands.accept_webhook(
                tenant_id=tenant_id,
                channel_connection_id=connection_id,
                webhook_event_id=self.uuid_factory(),
                content_id=self.uuid_factory(),
                outbox_job_id=self.uuid_factory(),
                audit_event_id=self.uuid_factory(),
                external_event_id=verified.external_event_id,
                provider_code=provider_code_for_kind(provider_kind),
                adapter_metadata=verified.adapter_metadata,
                plaintext=verified.raw_body,
                encoding=encoding,
                received_at=received_at,
                occurred_at=received_at,
                audit_context=audit_context,
                actor_type=AuditActorType.SERVICE,
                actor_id=self.service_actor_id,
            )
        except AtomicContentCommandUnavailableError as error:
            raise WebhookIngestionDeniedError(WEBHOOK_DENIED_RESPONSE) from error

        return WebhookAcceptanceResult(accepted=True, duplicate=result.duplicate)


def _encoding_for_content_type(content_type: str) -> ContentEncoding:
    normalized = content_type.split(";", maxsplit=1)[0].strip().lower()
    if normalized == "application/json":
        return ContentEncoding.JSON
    if normalized.startswith("text/"):
        return ContentEncoding.UTF8
    return ContentEncoding.BINARY
