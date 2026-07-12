"""Framework-independent conversation thread domain entity."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.canonical_enums import SalesCaseStatus


def _validate_uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")

    return value


def _validate_external_id(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    normalized_value = value.strip()

    if not normalized_value:
        raise ValueError(f"{field_name} must not be empty")

    if len(normalized_value) > 256:
        raise ValueError(f"{field_name} must not exceed 256 characters")

    return normalized_value


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")

    return value


@dataclass(slots=True)
class ConversationThread:
    id: UUID
    tenant_id: UUID
    channel_connection_id: UUID
    external_conversation_id: str
    sales_case_id: UUID | None
    lifecycle_status: SalesCaseStatus | None
    adapter_metadata: AdapterMetadata
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.channel_connection_id, "channel_connection_id")

        self.external_conversation_id = _validate_external_id(
            self.external_conversation_id,
            "external_conversation_id",
        )

        if self.sales_case_id is not None:
            _validate_uuid(self.sales_case_id, "sales_case_id")

        if self.sales_case_id is not None and self.lifecycle_status is not None:
            raise ValueError(
                "lifecycle_status must be omitted when conversation thread belongs to a sales case"
            )

        if self.lifecycle_status is not None and not isinstance(
            self.lifecycle_status,
            SalesCaseStatus,
        ):
            raise TypeError("lifecycle_status must be a SalesCaseStatus")

        if not isinstance(self.adapter_metadata, AdapterMetadata):
            raise TypeError("adapter_metadata must be an AdapterMetadata")

        self.created_at = _validate_timezone_aware_datetime(self.created_at, "created_at")
        self.updated_at = _validate_timezone_aware_datetime(self.updated_at, "updated_at")

        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
