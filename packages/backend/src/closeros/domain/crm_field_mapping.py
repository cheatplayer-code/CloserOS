"""Tenant-confirmed CRM field mapping domain records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class CrmFieldMappingStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class CrmFieldMapping:
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


__all__ = ["CrmFieldMapping", "CrmFieldMappingStatus"]
