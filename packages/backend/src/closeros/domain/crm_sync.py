"""CRM synchronization domain records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class CrmSyncDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CrmSyncStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CrmSyncAttemptStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CrmSyncCheckpoint:
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
class CrmSyncAttempt:
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


__all__ = [
    "CrmSyncAttempt",
    "CrmSyncAttemptStatus",
    "CrmSyncCheckpoint",
    "CrmSyncDirection",
    "CrmSyncStatus",
]
