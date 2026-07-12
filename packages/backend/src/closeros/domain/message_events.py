"""Framework-independent immutable message event domain entities."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.canonical_enums import DeliveryStatus


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


@dataclass(frozen=True, slots=True)
class MessageEditEvent:
    id: UUID
    tenant_id: UUID
    message_id: UUID
    external_event_id: str
    occurred_at: datetime
    content_id: UUID | None
    adapter_metadata: AdapterMetadata

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.message_id, "message_id")

        object.__setattr__(
            self,
            "external_event_id",
            _validate_external_id(self.external_event_id, "external_event_id"),
        )

        object.__setattr__(
            self,
            "occurred_at",
            _validate_timezone_aware_datetime(self.occurred_at, "occurred_at"),
        )

        if self.content_id is not None:
            _validate_uuid(self.content_id, "content_id")

        if not isinstance(self.adapter_metadata, AdapterMetadata):
            raise TypeError("adapter_metadata must be an AdapterMetadata")


@dataclass(frozen=True, slots=True)
class MessageDeletionEvent:
    id: UUID
    tenant_id: UUID
    message_id: UUID
    external_event_id: str
    occurred_at: datetime
    adapter_metadata: AdapterMetadata

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.message_id, "message_id")

        object.__setattr__(
            self,
            "external_event_id",
            _validate_external_id(self.external_event_id, "external_event_id"),
        )

        object.__setattr__(
            self,
            "occurred_at",
            _validate_timezone_aware_datetime(self.occurred_at, "occurred_at"),
        )

        if not isinstance(self.adapter_metadata, AdapterMetadata):
            raise TypeError("adapter_metadata must be an AdapterMetadata")


@dataclass(frozen=True, slots=True)
class MessageDeliveryStatusEvent:
    id: UUID
    tenant_id: UUID
    message_id: UUID
    external_event_id: str
    occurred_at: datetime
    delivery_status: DeliveryStatus
    adapter_metadata: AdapterMetadata

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.message_id, "message_id")

        object.__setattr__(
            self,
            "external_event_id",
            _validate_external_id(self.external_event_id, "external_event_id"),
        )

        object.__setattr__(
            self,
            "occurred_at",
            _validate_timezone_aware_datetime(self.occurred_at, "occurred_at"),
        )

        if not isinstance(self.delivery_status, DeliveryStatus):
            raise TypeError("delivery_status must be a DeliveryStatus")

        if not isinstance(self.adapter_metadata, AdapterMetadata):
            raise TypeError("adapter_metadata must be an AdapterMetadata")
