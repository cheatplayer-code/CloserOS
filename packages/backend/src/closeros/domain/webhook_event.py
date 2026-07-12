"""Framework-independent webhook event domain entity."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.canonical_enums import WebhookProcessingStatus


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
class WebhookEvent:
    id: UUID
    tenant_id: UUID
    channel_connection_id: UUID
    external_event_id: str
    processing_status: WebhookProcessingStatus
    received_at: datetime
    processed_at: datetime | None
    adapter_metadata: AdapterMetadata

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.channel_connection_id, "channel_connection_id")

        self.external_event_id = _validate_external_id(
            self.external_event_id,
            "external_event_id",
        )

        if not isinstance(self.processing_status, WebhookProcessingStatus):
            raise TypeError("processing_status must be a WebhookProcessingStatus")

        self.received_at = _validate_timezone_aware_datetime(self.received_at, "received_at")

        if self.processed_at is not None:
            self.processed_at = _validate_timezone_aware_datetime(
                self.processed_at,
                "processed_at",
            )

            if self.processed_at < self.received_at:
                raise ValueError("processed_at must not be earlier than received_at")

        if not isinstance(self.adapter_metadata, AdapterMetadata):
            raise TypeError("adapter_metadata must be an AdapterMetadata")
