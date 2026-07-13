"""Framework-independent notification delivery domain model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_RECIPIENT_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_TEMPLATE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class NotificationKind(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
    OUTBOUND_APPROVAL = "outbound_approval"
    SYSTEM_ALERT = "system_alert"


class NotificationDeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERING = "delivering"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NotificationAttemptOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TRANSIENT_FAILED = "transient_failed"


class NotificationTemplateCode(StrEnum):
    EMAIL_VERIFICATION_V1 = "email_verification_v1"
    PASSWORD_RESET_V1 = "password_reset_v1"


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


def _validate_recipient_hash(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("recipient_hash must be a string")
    normalized = value.strip().lower()
    if not _RECIPIENT_HASH_PATTERN.fullmatch(normalized):
        raise ValueError("recipient_hash format is invalid")
    return normalized


def _validate_template_code(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("template_code must be a string")
    normalized = value.strip().lower()
    if not _TEMPLATE_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("template_code format is invalid")
    return normalized


def _validate_template_version(value: object) -> int:
    if not isinstance(value, int) or value < 1:
        raise ValueError("template_version must be a positive integer")
    return value


def _validate_idempotency_key(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("idempotency_key must not be empty")
    if len(value.strip()) > 128:
        raise ValueError("idempotency_key exceeds maximum length")
    return value.strip()


@dataclass(frozen=True, slots=True)
class NotificationTemplate:
    subject: str
    body: str


def render_email_verification_template(*, verification_url: str) -> NotificationTemplate:
    if not isinstance(verification_url, str) or not verification_url.strip():
        raise ValueError("verification_url must not be empty")
    return NotificationTemplate(
        subject="Verify your CloserOS email address",
        body=(
            "Please verify your email address by opening the link below.\n\n"
            f"{verification_url.strip()}\n\n"
            "If you did not request this, you can ignore this message."
        ),
    )


def render_password_reset_template(*, reset_url: str) -> NotificationTemplate:
    if not isinstance(reset_url, str) or not reset_url.strip():
        raise ValueError("reset_url must not be empty")
    return NotificationTemplate(
        subject="Reset your CloserOS password",
        body=(
            "Use the link below to reset your password.\n\n"
            f"{reset_url.strip()}\n\n"
            "If you did not request this, you can ignore this message."
        ),
    )


@dataclass(frozen=True, slots=True)
class NotificationDelivery:
    id: UUID
    tenant_id: UUID | None
    payload_tenant_id: UUID | None
    kind: NotificationKind
    status: NotificationDeliveryStatus
    template_code: str
    template_version: int
    recipient_hash: str
    encrypted_payload_content_id: UUID | None
    idempotency_key: str
    attempt_count: int
    correlation_id: UUID | None
    created_at: datetime
    updated_at: datetime
    delivered_at: datetime | None = None
    last_error_code: str | None = None

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        if self.tenant_id is not None:
            _validate_uuid(self.tenant_id, "tenant_id")
        if self.payload_tenant_id is not None:
            _validate_uuid(self.payload_tenant_id, "payload_tenant_id")
        has_payload_tenant = self.payload_tenant_id is not None
        has_payload_content = self.encrypted_payload_content_id is not None
        if has_payload_tenant != has_payload_content:
            raise ValueError("payload reference must be fully linked or fully cleared")
        if not isinstance(self.kind, NotificationKind):
            raise TypeError("kind must be a NotificationKind")
        if not isinstance(self.status, NotificationDeliveryStatus):
            raise TypeError("status must be a NotificationDeliveryStatus")
        object.__setattr__(self, "template_code", _validate_template_code(self.template_code))
        object.__setattr__(
            self, "template_version", _validate_template_version(self.template_version)
        )
        object.__setattr__(self, "recipient_hash", _validate_recipient_hash(self.recipient_hash))
        if self.encrypted_payload_content_id is not None:
            _validate_uuid(self.encrypted_payload_content_id, "encrypted_payload_content_id")
        elif self.status is not NotificationDeliveryStatus.SUCCEEDED:
            raise ValueError("encrypted_payload_content_id is required unless delivery succeeded")
        object.__setattr__(self, "idempotency_key", _validate_idempotency_key(self.idempotency_key))
        if not isinstance(self.attempt_count, int) or self.attempt_count < 0:
            raise ValueError("attempt_count must be a non-negative integer")
        if self.correlation_id is not None:
            _validate_uuid(self.correlation_id, "correlation_id")
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
        if self.delivered_at is not None:
            object.__setattr__(
                self,
                "delivered_at",
                _validate_timezone_aware_datetime(self.delivered_at, "delivered_at"),
            )
        if self.last_error_code is not None and (
            not isinstance(self.last_error_code, str) or not self.last_error_code.strip()
        ):
            raise ValueError("last_error_code must be a non-empty string when present")

    def __repr__(self) -> str:
        return (
            "NotificationDelivery("
            f"id={self.id!s}, "
            f"kind={self.kind.value!r}, "
            f"status={self.status.value!r}"
            ")"
        )


__all__ = [
    "NotificationAttemptOutcome",
    "NotificationDelivery",
    "NotificationDeliveryStatus",
    "NotificationKind",
    "NotificationTemplate",
    "NotificationTemplateCode",
    "render_email_verification_template",
    "render_password_reset_template",
]
