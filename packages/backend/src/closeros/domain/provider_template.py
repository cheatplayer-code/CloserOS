"""Framework-independent provider message template metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_TEMPLATE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_LANGUAGE_CODE_PATTERN = re.compile(r"^[a-z]{2}(_[A-Z]{2})?$")
_MAX_PROVIDER_TEMPLATE_ID_LENGTH = 128
_MAX_CATEGORY_LENGTH = 32


class ProviderTemplateApprovalStatus(StrEnum):
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"
    PAUSED = "paused"
    DISABLED = "disabled"


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


def _validate_provider_template_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("provider_template_id must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("provider_template_id must not be empty")
    if len(normalized) > _MAX_PROVIDER_TEMPLATE_ID_LENGTH:
        raise ValueError("provider_template_id exceeds maximum length")
    return normalized


def _validate_template_name(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("name must be a string")
    normalized = value.strip().lower()
    if not _TEMPLATE_NAME_PATTERN.fullmatch(normalized):
        raise ValueError("name format is invalid")
    return normalized


def _validate_language_code(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("language_code must be a string")
    normalized = value.strip()
    if not _LANGUAGE_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("language_code format is invalid")
    return normalized


def _validate_category(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("category must be a string")
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("category must not be empty")
    if len(normalized) > _MAX_CATEGORY_LENGTH:
        raise ValueError("category exceeds maximum length")
    return normalized


def _validate_component_shape(value: object) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise TypeError("component_shape must be a sequence")
    if not value:
        raise ValueError("component_shape must not be empty")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError("component_shape items must be strings")
        code = item.strip().lower()
        if not code:
            raise ValueError("component_shape items must not be empty")
        normalized.append(code)
    return tuple(normalized)


def template_is_sendable(status: ProviderTemplateApprovalStatus) -> bool:
    return status is ProviderTemplateApprovalStatus.APPROVED


@dataclass(frozen=True, slots=True)
class ProviderMessageTemplate:
    id: UUID
    tenant_id: UUID
    whatsapp_connection_id: UUID
    provider_template_id: str
    name: str
    language_code: str
    category: str
    approval_status: ProviderTemplateApprovalStatus
    component_shape: tuple[str, ...]
    parameter_count: int
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.whatsapp_connection_id, "whatsapp_connection_id")

        object.__setattr__(
            self,
            "provider_template_id",
            _validate_provider_template_id(self.provider_template_id),
        )
        object.__setattr__(self, "name", _validate_template_name(self.name))
        object.__setattr__(self, "language_code", _validate_language_code(self.language_code))
        object.__setattr__(self, "category", _validate_category(self.category))

        if not isinstance(self.approval_status, ProviderTemplateApprovalStatus):
            raise TypeError("approval_status must be a ProviderTemplateApprovalStatus")

        object.__setattr__(
            self,
            "component_shape",
            _validate_component_shape(self.component_shape),
        )

        if not isinstance(self.parameter_count, int) or self.parameter_count < 0:
            raise ValueError("parameter_count must be a non-negative integer")

        object.__setattr__(
            self,
            "last_synced_at",
            _validate_timezone_aware_datetime(self.last_synced_at, "last_synced_at"),
        )
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

        if not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be a positive integer")

    def __repr__(self) -> str:
        return (
            "ProviderMessageTemplate("
            f"id={self.id!s}, "
            f"name={self.name!r}, "
            f"language_code={self.language_code!r}, "
            f"approval_status={self.approval_status.value!r}"
            ")"
        )


__all__ = [
    "ProviderMessageTemplate",
    "ProviderTemplateApprovalStatus",
    "template_is_sendable",
]
