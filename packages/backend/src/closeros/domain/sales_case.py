"""Framework-independent sales case domain entity."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.domain.canonical_enums import SalesCaseStatus


def _validate_uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")

    return value


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")

    return value


@dataclass(slots=True)
class SalesCase:
    id: UUID
    tenant_id: UUID
    status: SalesCaseStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")

        if not isinstance(self.status, SalesCaseStatus):
            raise TypeError("status must be a SalesCaseStatus")

        self.created_at = _validate_timezone_aware_datetime(self.created_at, "created_at")
        self.updated_at = _validate_timezone_aware_datetime(self.updated_at, "updated_at")

        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
