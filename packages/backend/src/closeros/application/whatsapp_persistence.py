"""Application persistence ports for WhatsApp Cloud connections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.provider_capability import ProviderCapability
from closeros.domain.whatsapp_cloud_connection import (
    WebhookSubscriptionStatus,
    WhatsAppCloudConnectionStatus,
)


class WhatsAppPersistenceError(PersistenceError):
    """Base class for WhatsApp persistence failures."""


class WhatsAppConnectionNotFoundError(WhatsAppPersistenceError):
    """Raised when a WhatsApp connection cannot be found."""


class WhatsAppConnectionVersionConflictError(WhatsAppPersistenceError):
    """Raised when optimistic concurrency detects a stale version."""


class DuplicateWhatsAppConnectionError(WhatsAppPersistenceError):
    """Raised when a duplicate WhatsApp connection would be created."""


@dataclass(frozen=True, slots=True)
class WhatsAppCloudConnectionRecord:
    id: UUID
    tenant_id: UUID
    channel_connection_id: UUID
    app_id: str
    waba_id: str
    phone_number_id: str
    display_phone_number: str | None
    graph_api_version: str
    access_token_ref: str | None
    app_secret_ref: str | None
    verify_token_ref: str | None
    status: WhatsAppCloudConnectionStatus
    webhook_subscription_status: WebhookSubscriptionStatus
    capabilities: frozenset[ProviderCapability]
    webhook_public_key: str
    created_at: datetime
    updated_at: datetime
    last_verified_at: datetime | None
    version: int


class WhatsAppCloudConnectionRepository(Protocol):
    async def add(self, *, record: WhatsAppCloudConnectionRecord) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> WhatsAppCloudConnectionRecord | None: ...

    async def get_by_id_for_update(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> WhatsAppCloudConnectionRecord | None: ...

    async def get_by_webhook_public_key(
        self,
        *,
        webhook_public_key: str,
    ) -> WhatsAppCloudConnectionRecord | None: ...

    async def list_by_tenant(
        self,
        *,
        tenant_id: UUID,
    ) -> tuple[WhatsAppCloudConnectionRecord, ...]: ...

    async def update(
        self,
        *,
        record: WhatsAppCloudConnectionRecord,
        expected_version: int,
    ) -> WhatsAppCloudConnectionRecord: ...
