"""Application persistence ports for provider message templates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.provider_template import ProviderTemplateApprovalStatus


class ProviderTemplatePersistenceError(PersistenceError):
    """Base class for provider template persistence failures."""


class ProviderTemplateNotFoundError(ProviderTemplatePersistenceError):
    """Raised when a provider template cannot be found."""


class ProviderTemplateVersionConflictError(ProviderTemplatePersistenceError):
    """Raised when optimistic concurrency detects a stale version."""


@dataclass(frozen=True, slots=True)
class ProviderMessageTemplateRecord:
    id: UUID
    tenant_id: UUID
    whatsapp_connection_id: UUID
    provider_template_id: str
    name: str
    language_code: str
    category: str
    approval_status: ProviderTemplateApprovalStatus
    component_shape: tuple[str, ...]
    parameter_count: int
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime
    version: int


class ProviderMessageTemplateRepository(Protocol):
    async def upsert(
        self, *, record: ProviderMessageTemplateRecord
    ) -> ProviderMessageTemplateRecord: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        template_id: UUID,
    ) -> ProviderMessageTemplateRecord | None: ...

    async def list_by_connection(
        self,
        *,
        tenant_id: UUID,
        whatsapp_connection_id: UUID,
    ) -> tuple[ProviderMessageTemplateRecord, ...]: ...
