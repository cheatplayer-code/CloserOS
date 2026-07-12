"""Application persistence ports for provider media references."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.provider_media_reference import MediaQuarantineStatus


class ProviderMediaPersistenceError(PersistenceError):
    """Base class for provider media persistence failures."""


class DuplicateProviderMediaReferenceError(ProviderMediaPersistenceError):
    """Raised when a duplicate provider media reference would be created."""


@dataclass(frozen=True, slots=True)
class ProviderMediaReferenceRecord:
    id: UUID
    tenant_id: UUID
    channel_connection_id: UUID
    conversation_thread_id: UUID
    inbound_message_id: UUID | None
    provider_media_id: str
    media_type: str
    mime_type: str | None
    size_bytes: int | None
    quarantine_status: MediaQuarantineStatus
    created_at: datetime
    updated_at: datetime


class ProviderMediaReferenceRepository(Protocol):
    async def add(self, *, record: ProviderMediaReferenceRecord) -> None: ...

    async def get_by_provider_media_id(
        self,
        *,
        tenant_id: UUID,
        channel_connection_id: UUID,
        provider_media_id: str,
    ) -> ProviderMediaReferenceRecord | None: ...

    async def list_for_thread(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID,
    ) -> tuple[ProviderMediaReferenceRecord, ...]: ...
