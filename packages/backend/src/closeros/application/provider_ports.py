"""Application ports for provider-neutral webhook ingestion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.canonical_enums import ProviderKind
from closeros.domain.normalized_operations import NormalizedOperation
from closeros.domain.provider_credentials import SecretBytes


class ProviderAdapterError(Exception):
    """Base class for safe provider adapter failures."""


class ProviderSignatureError(ProviderAdapterError):
    """Raised when webhook signature verification fails."""


class ProviderPayloadError(ProviderAdapterError):
    """Raised when provider payload cannot be normalized."""


@dataclass(frozen=True, slots=True)
class VerifiedWebhookResult:
    external_event_id: str
    received_content_type: str
    adapter_metadata: AdapterMetadata
    provider_event_at: datetime | None
    raw_body: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.external_event_id, str) or not self.external_event_id.strip():
            raise ValueError("external_event_id must not be empty")
        if (
            not isinstance(self.received_content_type, str)
            or not self.received_content_type.strip()
        ):
            raise ValueError("received_content_type must not be empty")
        if not isinstance(self.adapter_metadata, AdapterMetadata):
            raise TypeError("adapter_metadata must be an AdapterMetadata")
        if type(self.raw_body) is not bytes or not self.raw_body:
            raise ValueError("raw_body must be non-empty bytes")


class ProviderWebhookAdapter(Protocol):
    @property
    def provider_kind(self) -> ProviderKind: ...

    async def verify_webhook(
        self,
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
        connection_id: UUID,
        tenant_id: UUID,
    ) -> VerifiedWebhookResult: ...

    def normalize_payload(
        self,
        *,
        decrypted_payload: bytes,
        content_type: str,
    ) -> tuple[NormalizedOperation, ...]: ...


class ProviderCredentialResolver(Protocol):
    async def resolve_webhook_secret(
        self,
        *,
        tenant_id: UUID,
        channel_connection_id: UUID,
    ) -> bytes | None: ...


class WhatsAppCredentialResolver(Protocol):
    async def resolve_access_token(
        self,
        *,
        tenant_id: UUID,
        whatsapp_connection_id: UUID,
        reference_key: str,
    ) -> SecretBytes | None: ...

    async def resolve_app_secret(
        self,
        *,
        tenant_id: UUID,
        whatsapp_connection_id: UUID,
        reference_key: str,
    ) -> SecretBytes | None: ...

    async def resolve_verify_token(
        self,
        *,
        tenant_id: UUID,
        whatsapp_connection_id: UUID,
        reference_key: str,
    ) -> SecretBytes | None: ...


class WebhookRateLimiter(Protocol):
    async def check_webhook(
        self,
        *,
        scope_key: str,
        limit: int,
        window_seconds: int,
    ) -> bool: ...


class ImportContentScanner(Protocol):
    async def scan_csv_bytes(self, *, content: bytes) -> bool: ...
