"""Application persistence ports for CRM integrations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.crm_conflict import CrmConflictResolution, CrmConflictStatus
from closeros.domain.crm_connection import CrmConnectionStatus
from closeros.domain.crm_field_mapping import CrmFieldMappingStatus
from closeros.domain.crm_provider import CrmProviderCode
from closeros.domain.crm_sync import CrmSyncAttemptStatus, CrmSyncDirection


class CrmPersistenceError(PersistenceError):
    """Base class for CRM persistence failures."""


class CrmConnectionNotFoundError(CrmPersistenceError):
    """Raised when a CRM connection cannot be found."""


class CrmVersionConflictError(CrmPersistenceError):
    """Raised when optimistic concurrency detects a stale CRM record."""


class DuplicateCrmConnectionError(CrmPersistenceError):
    """Raised when a duplicate CRM connection would be created."""


@dataclass(frozen=True, slots=True)
class CrmConnectionRecord:
    id: UUID
    tenant_id: UUID
    provider: CrmProviderCode
    portal_domain: str | None
    client_id_ref: str | None
    client_secret_ref: str | None
    access_token_ref: str | None
    refresh_token_ref: str | None
    status: CrmConnectionStatus
    created_at: datetime
    updated_at: datetime
    last_verified_at: datetime | None
    last_successful_sync_at: datetime | None
    version: int


@dataclass(frozen=True, slots=True)
class CrmFieldMappingRecord:
    id: UUID
    tenant_id: UUID
    crm_connection_id: UUID
    external_object_type: str
    external_field_key: str
    closeros_field: str
    status: CrmFieldMappingStatus
    created_at: datetime
    updated_at: datetime
    confirmed_by_user_id: UUID | None
    version: int


@dataclass(frozen=True, slots=True)
class CrmSyncCheckpointRecord:
    id: UUID
    tenant_id: UUID
    crm_connection_id: UUID
    direction: CrmSyncDirection
    resource_type: str
    cursor: str | None
    last_synced_at: datetime | None
    updated_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class CrmSyncAttemptRecord:
    id: UUID
    tenant_id: UUID
    crm_connection_id: UUID
    direction: CrmSyncDirection
    status: CrmSyncAttemptStatus
    resource_type: str
    started_at: datetime
    finished_at: datetime | None
    records_seen: int
    records_changed: int
    error_code: str | None


@dataclass(frozen=True, slots=True)
class CrmConflictRecord:
    id: UUID
    tenant_id: UUID
    crm_connection_id: UUID
    external_object_type: str
    external_object_id: str
    field_key: str
    crm_value_hash: str
    closeros_value_hash: str
    status: CrmConflictStatus
    created_at: datetime
    resolved_at: datetime | None
    resolved_by_user_id: UUID | None
    resolution: CrmConflictResolution | None
    version: int


class CrmConnectionRepository(Protocol):
    async def add(self, *, record: CrmConnectionRecord) -> None: ...

    async def get_by_id(
        self, *, tenant_id: UUID, connection_id: UUID
    ) -> CrmConnectionRecord | None: ...

    async def get_by_id_for_update(
        self, *, tenant_id: UUID, connection_id: UUID
    ) -> CrmConnectionRecord | None: ...

    async def list_by_tenant(self, *, tenant_id: UUID) -> tuple[CrmConnectionRecord, ...]: ...

    async def update(
        self, *, record: CrmConnectionRecord, expected_version: int
    ) -> CrmConnectionRecord: ...


class CrmFieldMappingRepository(Protocol):
    async def upsert(self, *, record: CrmFieldMappingRecord) -> CrmFieldMappingRecord: ...

    async def list_by_connection(
        self, *, tenant_id: UUID, crm_connection_id: UUID
    ) -> tuple[CrmFieldMappingRecord, ...]: ...


class CrmSyncCheckpointRepository(Protocol):
    async def get(
        self,
        *,
        tenant_id: UUID,
        crm_connection_id: UUID,
        direction: CrmSyncDirection,
        resource_type: str,
    ) -> CrmSyncCheckpointRecord | None: ...

    async def upsert(self, *, record: CrmSyncCheckpointRecord) -> CrmSyncCheckpointRecord: ...


class CrmSyncAttemptRepository(Protocol):
    async def append(self, *, record: CrmSyncAttemptRecord) -> None: ...

    async def list_recent(
        self, *, tenant_id: UUID, crm_connection_id: UUID, limit: int
    ) -> tuple[CrmSyncAttemptRecord, ...]: ...


class CrmConflictRepository(Protocol):
    async def add(self, *, record: CrmConflictRecord) -> None: ...

    async def list_open(
        self, *, tenant_id: UUID, crm_connection_id: UUID
    ) -> tuple[CrmConflictRecord, ...]: ...

    async def get_by_id_for_update(
        self, *, tenant_id: UUID, conflict_id: UUID
    ) -> CrmConflictRecord | None: ...

    async def update(
        self, *, record: CrmConflictRecord, expected_version: int
    ) -> CrmConflictRecord: ...


__all__ = [
    "CrmConflictRecord",
    "CrmConflictRepository",
    "CrmConnectionNotFoundError",
    "CrmConnectionRecord",
    "CrmConnectionRepository",
    "CrmFieldMappingRecord",
    "CrmFieldMappingRepository",
    "CrmPersistenceError",
    "CrmSyncAttemptRecord",
    "CrmSyncAttemptRepository",
    "CrmSyncCheckpointRecord",
    "CrmSyncCheckpointRepository",
    "CrmVersionConflictError",
    "DuplicateCrmConnectionError",
]
