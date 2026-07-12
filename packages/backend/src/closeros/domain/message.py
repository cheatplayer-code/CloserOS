"""Framework-independent immutable message domain entity."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.canonical_enums import MessageDirection, ParticipantSenderType


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
class Message:
    id: UUID
    tenant_id: UUID
    conversation_thread_id: UUID
    external_message_id: str
    sender_type: ParticipantSenderType
    direction: MessageDirection
    sent_at: datetime
    received_at: datetime
    content_id: UUID | None
    reply_to_message_id: UUID | None
    adapter_metadata: AdapterMetadata

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.conversation_thread_id, "conversation_thread_id")

        object.__setattr__(
            self,
            "external_message_id",
            _validate_external_id(self.external_message_id, "external_message_id"),
        )

        if not isinstance(self.sender_type, ParticipantSenderType):
            raise TypeError("sender_type must be a ParticipantSenderType")

        if not isinstance(self.direction, MessageDirection):
            raise TypeError("direction must be a MessageDirection")

        sent_at = _validate_timezone_aware_datetime(self.sent_at, "sent_at")
        received_at = _validate_timezone_aware_datetime(self.received_at, "received_at")

        if received_at < sent_at:
            raise ValueError("received_at must not be earlier than sent_at")

        object.__setattr__(self, "sent_at", sent_at)
        object.__setattr__(self, "received_at", received_at)

        if self.content_id is not None:
            _validate_uuid(self.content_id, "content_id")

        if self.reply_to_message_id is not None:
            _validate_uuid(self.reply_to_message_id, "reply_to_message_id")

        if not isinstance(self.adapter_metadata, AdapterMetadata):
            raise TypeError("adapter_metadata must be an AdapterMetadata")
