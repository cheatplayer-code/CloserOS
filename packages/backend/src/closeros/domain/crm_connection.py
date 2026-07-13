"""CRM connection domain model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from closeros.domain.crm_provider import CrmProviderCode

_REFERENCE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_DOMAIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{0,253}$")


class CrmConnectionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEGRADED = "degraded"
    REAUTHORIZATION_REQUIRED = "reauthorization_required"
    REVOKED = "revoked"
    DISABLED = "disabled"


class CrmConnectionError(ValueError):
    """Raised when a CRM connection violates domain invariants."""


def _validate_uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")
    return value


def _validate_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _validate_reference(value: object | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not _REFERENCE_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} format is invalid")
    return normalized


def _validate_domain(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("portal_domain must be a string")
    normalized = value.strip().lower()
    if not _DOMAIN_PATTERN.fullmatch(normalized):
        raise ValueError("portal_domain format is invalid")
    return normalized


def crm_connection_requires_credentials(status: CrmConnectionStatus) -> bool:
    return status in {
        CrmConnectionStatus.ACTIVE,
        CrmConnectionStatus.DEGRADED,
        CrmConnectionStatus.REAUTHORIZATION_REQUIRED,
    }


@dataclass(frozen=True, slots=True)
class CrmConnection:
    id: UUID
    tenant_id: UUID
    provider: CrmProviderCode
    portal_domain: str | None
    client_id_ref: str | None
    client_secret_ref: str | None
    access_token_ref: str | None
    refresh_token_ref: str | None
    status: CrmConnectionStatus
    created_at: datetime
    updated_at: datetime
    last_verified_at: datetime | None
    last_successful_sync_at: datetime | None
    version: int

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        if not isinstance(self.provider, CrmProviderCode):
            raise TypeError("provider must be a CrmProviderCode")
        object.__setattr__(self, "portal_domain", _validate_domain(self.portal_domain))
        object.__setattr__(
            self, "client_id_ref", _validate_reference(self.client_id_ref, "client_id_ref")
        )
        object.__setattr__(
            self,
            "client_secret_ref",
            _validate_reference(self.client_secret_ref, "client_secret_ref"),
        )
        object.__setattr__(
            self,
            "access_token_ref",
            _validate_reference(self.access_token_ref, "access_token_ref"),
        )
        object.__setattr__(
            self,
            "refresh_token_ref",
            _validate_reference(self.refresh_token_ref, "refresh_token_ref"),
        )
        if not isinstance(self.status, CrmConnectionStatus):
            raise TypeError("status must be a CrmConnectionStatus")
        object.__setattr__(self, "created_at", _validate_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _validate_datetime(self.updated_at, "updated_at"))
        if self.updated_at < self.created_at:
            raise CrmConnectionError("updated_at must not be earlier than created_at")
        if self.last_verified_at is not None:
            _validate_datetime(self.last_verified_at, "last_verified_at")
        if self.last_successful_sync_at is not None:
            _validate_datetime(self.last_successful_sync_at, "last_successful_sync_at")
        if not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if crm_connection_requires_credentials(self.status) and self.access_token_ref is None:
            raise CrmConnectionError("active CRM connections require access_token_ref")


__all__ = [
    "CrmConnection",
    "CrmConnectionError",
    "CrmConnectionStatus",
    "crm_connection_requires_credentials",
]
