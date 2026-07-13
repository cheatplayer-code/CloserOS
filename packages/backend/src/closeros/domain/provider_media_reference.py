"""Framework-independent provider media reference and quarantine model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_MEDIA_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_MIME_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9.+-]{0,127}$")
_MAX_PROVIDER_MEDIA_ID_LENGTH = 128
_MAX_SIZE_BYTES = 100 * 1024 * 1024
_SUPPORTED_PROVIDER_MEDIA_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "audio/aac",
        "audio/mp4",
        "audio/mpeg",
        "audio/amr",
        "audio/ogg",
        "video/mp4",
        "video/3gpp",
        "application/pdf",
        "application/vnd.ms-powerpoint",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain",
    }
)


def is_supported_provider_media_mime(mime_type: str | None) -> bool:
    if mime_type is None:
        return False
    if not isinstance(mime_type, str):
        raise TypeError("mime_type must be a string")
    normalized = mime_type.strip().lower()
    if not normalized:
        return False
    return normalized in _SUPPORTED_PROVIDER_MEDIA_MIME_TYPES


class MediaQuarantineStatus(StrEnum):
    FETCHING = "fetching"
    FETCH_FAILED = "fetch_failed"
    FETCH_UNAVAILABLE = "fetch_unavailable"
    QUARANTINED_PENDING_SCAN = "quarantined_pending_scan"
    SCANNING = "scanning"
    CLEAN = "clean"
    INFECTED = "infected"
    SCAN_PASSED = "scan_passed"
    SCAN_FAILED = "scan_failed"


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


def _validate_media_type(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("media_type must be a string")
    normalized = value.strip().lower()
    if not _MEDIA_TYPE_PATTERN.fullmatch(normalized):
        raise ValueError("media_type format is invalid")
    return normalized


def _validate_mime_type(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("mime_type must be a string")
    normalized = value.strip().lower()
    if not _MIME_TYPE_PATTERN.fullmatch(normalized):
        raise ValueError("mime_type format is invalid")
    return normalized


def _validate_provider_media_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("provider_media_id must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("provider_media_id must not be empty")
    if len(normalized) > _MAX_PROVIDER_MEDIA_ID_LENGTH:
        raise ValueError("provider_media_id exceeds maximum length")
    return normalized


def _validate_size_bytes(value: object | None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value < 0:
        raise ValueError("size_bytes must be a non-negative integer")
    if value > _MAX_SIZE_BYTES:
        raise ValueError("size_bytes exceeds maximum allowed value")
    return value


@dataclass(frozen=True, slots=True)
class ProviderMediaReference:
    id: UUID
    tenant_id: UUID
    channel_connection_id: UUID
    conversation_thread_id: UUID
    inbound_message_id: UUID | None
    provider_media_id: str = field(repr=False)
    media_type: str
    mime_type: str | None
    size_bytes: int | None
    quarantine_status: MediaQuarantineStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.channel_connection_id, "channel_connection_id")
        _validate_uuid(self.conversation_thread_id, "conversation_thread_id")
        if self.inbound_message_id is not None:
            _validate_uuid(self.inbound_message_id, "inbound_message_id")

        object.__setattr__(
            self,
            "provider_media_id",
            _validate_provider_media_id(self.provider_media_id),
        )
        object.__setattr__(self, "media_type", _validate_media_type(self.media_type))
        object.__setattr__(self, "mime_type", _validate_mime_type(self.mime_type))
        object.__setattr__(self, "size_bytes", _validate_size_bytes(self.size_bytes))

        if not isinstance(self.quarantine_status, MediaQuarantineStatus):
            raise TypeError("quarantine_status must be a MediaQuarantineStatus")

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
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")

    def __repr__(self) -> str:
        return (
            "ProviderMediaReference("
            f"id={self.id!s}, "
            f"media_type={self.media_type!r}, "
            f"quarantine_status={self.quarantine_status.value!r}"
            ")"
        )


__all__ = [
    "MediaQuarantineStatus",
    "ProviderMediaReference",
    "is_supported_provider_media_mime",
]
