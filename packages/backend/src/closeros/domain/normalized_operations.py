"""Transient normalized provider operation types for webhook ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.canonical_enums import (
    DeliveryStatus,
    MessageDirection,
    ParticipantSenderType,
)

_MAX_NORMALIZED_OPERATIONS = 500


class NormalizedOperationKind(StrEnum):
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_EDITED = "message_edited"
    MESSAGE_DELETED = "message_deleted"
    DELIVERY_STATUS_CHANGED = "delivery_status_changed"


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
class NormalizedMessageReceived:
    external_conversation_id: str
    external_message_id: str
    sender_type: ParticipantSenderType
    direction: MessageDirection
    sent_at: datetime
    received_at: datetime
    reply_to_external_message_id: str | None
    adapter_metadata: AdapterMetadata
    raw_message_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "external_conversation_id",
            _validate_external_id(self.external_conversation_id, "external_conversation_id"),
        )
        object.__setattr__(
            self,
            "external_message_id",
            _validate_external_id(self.external_message_id, "external_message_id"),
        )
        if not isinstance(self.sender_type, ParticipantSenderType):
            raise TypeError("sender_type must be a ParticipantSenderType")
        if not isinstance(self.direction, MessageDirection):
            raise TypeError("direction must be a MessageDirection")
        object.__setattr__(
            self, "sent_at", _validate_timezone_aware_datetime(self.sent_at, "sent_at")
        )
        object.__setattr__(
            self,
            "received_at",
            _validate_timezone_aware_datetime(self.received_at, "received_at"),
        )
        if self.received_at < self.sent_at:
            raise ValueError("received_at must not be earlier than sent_at")
        if self.reply_to_external_message_id is not None:
            object.__setattr__(
                self,
                "reply_to_external_message_id",
                _validate_external_id(
                    self.reply_to_external_message_id,
                    "reply_to_external_message_id",
                ),
            )
        if not isinstance(self.adapter_metadata, AdapterMetadata):
            raise TypeError("adapter_metadata must be an AdapterMetadata")
        if type(self.raw_message_bytes) is not bytes or not self.raw_message_bytes:
            raise ValueError("raw_message_bytes must be non-empty bytes")


@dataclass(frozen=True, slots=True)
class NormalizedMessageEdited:
    external_conversation_id: str
    external_message_id: str
    external_event_id: str
    occurred_at: datetime
    adapter_metadata: AdapterMetadata
    replacement_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "external_conversation_id",
            _validate_external_id(self.external_conversation_id, "external_conversation_id"),
        )
        object.__setattr__(
            self,
            "external_message_id",
            _validate_external_id(self.external_message_id, "external_message_id"),
        )
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
        if type(self.replacement_bytes) is not bytes or not self.replacement_bytes:
            raise ValueError("replacement_bytes must be non-empty bytes")


@dataclass(frozen=True, slots=True)
class NormalizedMessageDeleted:
    external_conversation_id: str
    external_message_id: str
    external_event_id: str
    occurred_at: datetime
    adapter_metadata: AdapterMetadata

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "external_conversation_id",
            _validate_external_id(self.external_conversation_id, "external_conversation_id"),
        )
        object.__setattr__(
            self,
            "external_message_id",
            _validate_external_id(self.external_message_id, "external_message_id"),
        )
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
class NormalizedDeliveryStatusChanged:
    external_conversation_id: str
    external_message_id: str
    external_event_id: str
    delivery_status: DeliveryStatus
    occurred_at: datetime
    adapter_metadata: AdapterMetadata

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "external_conversation_id",
            _validate_external_id(self.external_conversation_id, "external_conversation_id"),
        )
        object.__setattr__(
            self,
            "external_message_id",
            _validate_external_id(self.external_message_id, "external_message_id"),
        )
        object.__setattr__(
            self,
            "external_event_id",
            _validate_external_id(self.external_event_id, "external_event_id"),
        )
        if not isinstance(self.delivery_status, DeliveryStatus):
            raise TypeError("delivery_status must be a DeliveryStatus")
        object.__setattr__(
            self,
            "occurred_at",
            _validate_timezone_aware_datetime(self.occurred_at, "occurred_at"),
        )
        if not isinstance(self.adapter_metadata, AdapterMetadata):
            raise TypeError("adapter_metadata must be an AdapterMetadata")


NormalizedOperation = (
    NormalizedMessageReceived
    | NormalizedMessageEdited
    | NormalizedMessageDeleted
    | NormalizedDeliveryStatusChanged
)


def validate_normalized_operations(
    operations: tuple[NormalizedOperation, ...],
) -> tuple[NormalizedOperation, ...]:
    if not isinstance(operations, tuple):
        raise TypeError("operations must be a tuple")

    if len(operations) > _MAX_NORMALIZED_OPERATIONS:
        raise ValueError("normalized operations exceed allowed limit")

    for operation in operations:
        if not isinstance(
            operation,
            (
                NormalizedMessageReceived,
                NormalizedMessageEdited,
                NormalizedMessageDeleted,
                NormalizedDeliveryStatusChanged,
            ),
        ):
            raise TypeError("operation type is not supported")

    return operations
