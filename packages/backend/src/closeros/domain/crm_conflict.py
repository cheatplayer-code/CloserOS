"""CRM synchronization conflict domain records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class CrmConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class CrmConflictResolution(StrEnum):
    USE_CRM = "use_crm"
    USE_CLOSEROS = "use_closeros"
    IGNORE = "ignore"


@dataclass(frozen=True, slots=True)
class CrmConflict:
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


__all__ = ["CrmConflict", "CrmConflictResolution", "CrmConflictStatus"]
