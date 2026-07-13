"""Framework-independent legal hold domain model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_REASON_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_REASON_DETAIL_MAX_LENGTH = 2_048


class LegalHoldStatus(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"


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


def _validate_reason_code(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("reason_code must be a string")
    normalized = value.strip().lower()
    if not _REASON_PATTERN.fullmatch(normalized):
        raise ValueError("reason_code format is invalid")
    return normalized


def _validate_reason_detail(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("reason_detail must be a string")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > _REASON_DETAIL_MAX_LENGTH:
        raise ValueError("reason_detail exceeds maximum length")
    return normalized


@dataclass(frozen=True, slots=True)
class LegalHold:
    id: UUID
    tenant_id: UUID
    status: LegalHoldStatus
    reason_code: str
    reason_detail: str | None
    created_by_user_id: UUID
    released_by_user_id: UUID | None
    created_at: datetime
    released_at: datetime | None
    updated_at: datetime

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        if not isinstance(self.status, LegalHoldStatus):
            raise TypeError("status must be a LegalHoldStatus")
        object.__setattr__(self, "reason_code", _validate_reason_code(self.reason_code))
        object.__setattr__(
            self,
            "reason_detail",
            _validate_reason_detail(self.reason_detail),
        )
        _validate_uuid(self.created_by_user_id, "created_by_user_id")
        if self.released_by_user_id is not None:
            _validate_uuid(self.released_by_user_id, "released_by_user_id")
        object.__setattr__(
            self,
            "created_at",
            _validate_timezone_aware_datetime(self.created_at, "created_at"),
        )
        if self.released_at is not None:
            object.__setattr__(
                self,
                "released_at",
                _validate_timezone_aware_datetime(self.released_at, "released_at"),
            )
        object.__setattr__(
            self,
            "updated_at",
            _validate_timezone_aware_datetime(self.updated_at, "updated_at"),
        )
        if self.status is LegalHoldStatus.ACTIVE and self.released_at is not None:
            raise ValueError("active legal holds must not have released_at")
        if self.status is LegalHoldStatus.RELEASED and self.released_at is None:
            raise ValueError("released legal holds require released_at")

    def __repr__(self) -> str:
        return (
            f"LegalHold(id={self.id!s}, tenant_id={self.tenant_id!s}, status={self.status.value!r})"
        )


__all__ = ["LegalHold", "LegalHoldStatus"]
