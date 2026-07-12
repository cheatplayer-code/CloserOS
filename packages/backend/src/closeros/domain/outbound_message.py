"""Framework-independent outbound message domain model and state machine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_FAILURE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_PROVIDER_MESSAGE_ID_LENGTH = 128


class OutboundMessageKind(StrEnum):
    FREE_FORM_TEXT = "free_form_text"
    APPROVED_TEMPLATE = "approved_template"


class OutboundMessageStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    QUEUED = "queued"
    SENDING = "sending"
    PROVIDER_ACCEPTED = "provider_accepted"
    DELIVERY_UNKNOWN = "delivery_unknown"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = frozenset(
    {
        OutboundMessageStatus.PROVIDER_ACCEPTED,
        OutboundMessageStatus.DELIVERY_UNKNOWN,
        OutboundMessageStatus.DELIVERED,
        OutboundMessageStatus.READ,
        OutboundMessageStatus.FAILED,
        OutboundMessageStatus.CANCELLED,
    }
)

_NO_RESEND_STATUSES = frozenset(
    {
        OutboundMessageStatus.PROVIDER_ACCEPTED,
        OutboundMessageStatus.DELIVERY_UNKNOWN,
        OutboundMessageStatus.DELIVERED,
        OutboundMessageStatus.READ,
    }
)

_ALLOWED_TRANSITIONS: dict[OutboundMessageStatus, frozenset[OutboundMessageStatus]] = {
    OutboundMessageStatus.DRAFT: frozenset(
        {OutboundMessageStatus.PENDING_APPROVAL, OutboundMessageStatus.CANCELLED}
    ),
    OutboundMessageStatus.PENDING_APPROVAL: frozenset(
        {OutboundMessageStatus.APPROVED, OutboundMessageStatus.CANCELLED}
    ),
    OutboundMessageStatus.APPROVED: frozenset(
        {OutboundMessageStatus.QUEUED, OutboundMessageStatus.CANCELLED}
    ),
    OutboundMessageStatus.QUEUED: frozenset(
        {OutboundMessageStatus.SENDING, OutboundMessageStatus.CANCELLED}
    ),
    OutboundMessageStatus.SENDING: frozenset(
        {
            OutboundMessageStatus.PROVIDER_ACCEPTED,
            OutboundMessageStatus.DELIVERY_UNKNOWN,
            OutboundMessageStatus.FAILED,
        }
    ),
    OutboundMessageStatus.PROVIDER_ACCEPTED: frozenset(
        {OutboundMessageStatus.DELIVERED, OutboundMessageStatus.READ, OutboundMessageStatus.FAILED}
    ),
    OutboundMessageStatus.DELIVERY_UNKNOWN: frozenset(
        {
            OutboundMessageStatus.PROVIDER_ACCEPTED,
            OutboundMessageStatus.DELIVERED,
            OutboundMessageStatus.READ,
            OutboundMessageStatus.FAILED,
        }
    ),
    OutboundMessageStatus.DELIVERED: frozenset({OutboundMessageStatus.READ}),
    OutboundMessageStatus.READ: frozenset(),
    OutboundMessageStatus.FAILED: frozenset(),
    OutboundMessageStatus.CANCELLED: frozenset(),
}


class OutboundMessageTransitionError(ValueError):
    """Raised when an outbound message state transition is not allowed."""


class OutboundMessageInvariantError(ValueError):
    """Raised when outbound message invariants are violated."""


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


def _validate_failure_code(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("failure_code must be a string")
    normalized = value.strip()
    if not _FAILURE_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("failure_code format is invalid")
    return normalized


def _validate_provider_message_id(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("provider_message_id must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("provider_message_id must not be empty")
    if len(normalized) > _MAX_PROVIDER_MESSAGE_ID_LENGTH:
        raise ValueError("provider_message_id exceeds maximum length")
    return normalized


def validate_outbound_message_transition(
    *,
    current: OutboundMessageStatus,
    target: OutboundMessageStatus,
) -> None:
    if current is target:
        return
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise OutboundMessageTransitionError("outbound message transition is not allowed")


def outbound_send_may_proceed(status: OutboundMessageStatus) -> bool:
    return status is OutboundMessageStatus.QUEUED


def outbound_is_terminal(status: OutboundMessageStatus) -> bool:
    return status in _TERMINAL_STATUSES


def outbound_resend_prohibited(status: OutboundMessageStatus) -> bool:
    return status in _NO_RESEND_STATUSES


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    id: UUID
    tenant_id: UUID
    conversation_thread_id: UUID
    channel_connection_id: UUID
    kind: OutboundMessageKind
    status: OutboundMessageStatus
    encrypted_content_id: UUID
    provider_template_id: UUID | None
    created_by_user_id: UUID
    approved_by_user_id: UUID | None
    failure_code: str | None
    created_at: datetime
    approved_at: datetime | None
    queued_at: datetime | None
    sent_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    version: int
    provider_message_id: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.conversation_thread_id, "conversation_thread_id")
        _validate_uuid(self.channel_connection_id, "channel_connection_id")
        _validate_uuid(self.encrypted_content_id, "encrypted_content_id")

        if not isinstance(self.kind, OutboundMessageKind):
            raise TypeError("kind must be an OutboundMessageKind")
        if not isinstance(self.status, OutboundMessageStatus):
            raise TypeError("status must be an OutboundMessageStatus")

        if self.kind is OutboundMessageKind.APPROVED_TEMPLATE:
            if self.provider_template_id is None:
                raise OutboundMessageInvariantError(
                    "approved template messages require provider_template_id"
                )
        elif self.provider_template_id is not None:
            raise OutboundMessageInvariantError(
                "free-form messages must not reference provider_template_id"
            )

        if self.provider_template_id is not None:
            _validate_uuid(self.provider_template_id, "provider_template_id")

        _validate_uuid(self.created_by_user_id, "created_by_user_id")
        if self.approved_by_user_id is not None:
            _validate_uuid(self.approved_by_user_id, "approved_by_user_id")

        if (
            self.status
            in {
                OutboundMessageStatus.APPROVED,
                OutboundMessageStatus.QUEUED,
                OutboundMessageStatus.SENDING,
                OutboundMessageStatus.PROVIDER_ACCEPTED,
                OutboundMessageStatus.DELIVERY_UNKNOWN,
                OutboundMessageStatus.DELIVERED,
                OutboundMessageStatus.READ,
            }
            and self.approved_by_user_id is None
        ):
            raise OutboundMessageInvariantError("approved messages require approved_by_user_id")

        object.__setattr__(
            self,
            "provider_message_id",
            _validate_provider_message_id(self.provider_message_id),
        )
        object.__setattr__(self, "failure_code", _validate_failure_code(self.failure_code))

        object.__setattr__(
            self,
            "created_at",
            _validate_timezone_aware_datetime(self.created_at, "created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _validate_timezone_aware_datetime(self.updated_at, "updated_at"),
        )
        for field_name in ("approved_at", "queued_at", "sent_at", "completed_at"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _validate_timezone_aware_datetime(value, field_name),
                )

        if not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be a positive integer")

        if self.status is OutboundMessageStatus.FAILED and self.failure_code is None:
            raise OutboundMessageInvariantError("failed messages require failure_code")

    def __repr__(self) -> str:
        return (
            "OutboundMessage("
            f"id={self.id!s}, "
            f"kind={self.kind.value!r}, "
            f"status={self.status.value!r}, "
            f"version={self.version}"
            ")"
        )


__all__ = [
    "OutboundMessage",
    "OutboundMessageInvariantError",
    "OutboundMessageKind",
    "OutboundMessageStatus",
    "OutboundMessageTransitionError",
    "outbound_is_terminal",
    "outbound_resend_prohibited",
    "outbound_send_may_proceed",
    "validate_outbound_message_transition",
]
