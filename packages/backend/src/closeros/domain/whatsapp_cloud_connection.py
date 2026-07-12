"""Framework-independent WhatsApp Cloud connection domain model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from closeros.domain.canonical_enums import ProviderKind
from closeros.domain.provider_capability import ProviderCapability

_REFERENCE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_WEBHOOK_PUBLIC_KEY_PATTERN = re.compile(r"^[a-z0-9]{32,64}$")
_MAX_PROVIDER_ID_LENGTH = 64
_MAX_DISPLAY_PHONE_LENGTH = 32
_MAX_GRAPH_API_VERSION_LENGTH = 16
_GRAPH_API_VERSION_PATTERN = re.compile(r"^v\d+\.\d+$")

_WHATSAPP_CLOUD_CAPABILITIES = frozenset(
    {
        ProviderCapability.INBOUND_TEXT,
        ProviderCapability.INTERACTIVE_REPLY,
        ProviderCapability.REACTION,
        ProviderCapability.MESSAGE_STATUS,
        ProviderCapability.MEDIA_REFERENCE,
        ProviderCapability.OUTBOUND_FREE_FORM_TEXT,
        ProviderCapability.OUTBOUND_APPROVED_TEMPLATE,
    }
)


class WhatsAppCloudConnectionStatus(StrEnum):
    DRAFT = "draft"
    VERIFICATION_PENDING = "verification_pending"
    ACTIVE = "active"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class WebhookSubscriptionStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    PENDING = "pending"
    SUBSCRIBED = "subscribed"
    FAILED = "failed"


_ACTIVE_STATUSES = frozenset(
    {
        WhatsAppCloudConnectionStatus.ACTIVE,
        WhatsAppCloudConnectionStatus.DEGRADED,
        WhatsAppCloudConnectionStatus.VERIFICATION_PENDING,
    }
)


class WhatsAppCloudConnectionError(ValueError):
    """Raised when WhatsApp connection domain validation fails."""


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


def _validate_provider_id(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) > _MAX_PROVIDER_ID_LENGTH:
        raise ValueError(f"{field_name} exceeds maximum length")
    if not normalized.isdigit():
        raise ValueError(f"{field_name} must contain only digits")
    return normalized


def _validate_reference(value: object | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if not _REFERENCE_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} format is invalid")
    return normalized


def _validate_webhook_public_key(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("webhook_public_key must be a string")
    normalized = value.strip()
    if not _WEBHOOK_PUBLIC_KEY_PATTERN.fullmatch(normalized):
        raise ValueError("webhook_public_key format is invalid")
    return normalized


def _validate_graph_api_version(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("graph_api_version must be a string")
    normalized = value.strip()
    if not _GRAPH_API_VERSION_PATTERN.fullmatch(normalized):
        raise ValueError("graph_api_version format is invalid")
    if len(normalized) > _MAX_GRAPH_API_VERSION_LENGTH:
        raise ValueError("graph_api_version exceeds maximum length")
    return normalized


def _validate_capabilities(value: object) -> frozenset[ProviderCapability]:
    if not isinstance(value, (frozenset, set, tuple, list)):
        raise TypeError("capabilities must be a collection")
    capabilities: set[ProviderCapability] = set()
    for item in value:
        if not isinstance(item, ProviderCapability):
            raise TypeError("capabilities must contain ProviderCapability values")
        capabilities.add(item)
    if not capabilities:
        raise ValueError("capabilities must not be empty")
    if not capabilities.issubset(_WHATSAPP_CLOUD_CAPABILITIES):
        raise ValueError("capabilities contain unsupported values")
    return frozenset(capabilities)


def _validate_version(value: object) -> int:
    if not isinstance(value, int) or value < 1:
        raise ValueError("version must be a positive integer")
    return value


def connection_allows_ingestion(status: WhatsAppCloudConnectionStatus) -> bool:
    return status in _ACTIVE_STATUSES


def connection_allows_outbound(status: WhatsAppCloudConnectionStatus) -> bool:
    return status is WhatsAppCloudConnectionStatus.ACTIVE


def connection_requires_credentials(status: WhatsAppCloudConnectionStatus) -> bool:
    return status in {
        WhatsAppCloudConnectionStatus.ACTIVE,
        WhatsAppCloudConnectionStatus.DEGRADED,
        WhatsAppCloudConnectionStatus.VERIFICATION_PENDING,
    }


@dataclass(frozen=True, slots=True)
class WhatsAppCloudConnection:
    id: UUID
    tenant_id: UUID
    channel_connection_id: UUID
    provider: ProviderKind
    app_id: str
    waba_id: str
    phone_number_id: str
    display_phone_number: str | None
    graph_api_version: str
    access_token_ref: str | None
    app_secret_ref: str | None
    verify_token_ref: str | None
    status: WhatsAppCloudConnectionStatus
    webhook_subscription_status: WebhookSubscriptionStatus
    capabilities: frozenset[ProviderCapability]
    webhook_public_key: str
    created_at: datetime
    updated_at: datetime
    last_verified_at: datetime | None
    version: int

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.channel_connection_id, "channel_connection_id")

        if self.provider is not ProviderKind.WHATSAPP_CLOUD:
            raise ValueError("provider must be whatsapp_cloud")

        object.__setattr__(self, "app_id", _validate_provider_id(self.app_id, "app_id"))
        object.__setattr__(self, "waba_id", _validate_provider_id(self.waba_id, "waba_id"))
        object.__setattr__(
            self,
            "phone_number_id",
            _validate_provider_id(self.phone_number_id, "phone_number_id"),
        )

        if self.display_phone_number is not None:
            if not isinstance(self.display_phone_number, str):
                raise TypeError("display_phone_number must be a string")
            normalized_display = self.display_phone_number.strip()
            if not normalized_display:
                raise ValueError("display_phone_number must not be empty")
            if len(normalized_display) > _MAX_DISPLAY_PHONE_LENGTH:
                raise ValueError("display_phone_number exceeds maximum length")
            object.__setattr__(self, "display_phone_number", normalized_display)

        object.__setattr__(
            self,
            "graph_api_version",
            _validate_graph_api_version(self.graph_api_version),
        )
        object.__setattr__(
            self,
            "access_token_ref",
            _validate_reference(self.access_token_ref, "access_token_ref"),
        )
        object.__setattr__(
            self,
            "app_secret_ref",
            _validate_reference(self.app_secret_ref, "app_secret_ref"),
        )
        object.__setattr__(
            self,
            "verify_token_ref",
            _validate_reference(self.verify_token_ref, "verify_token_ref"),
        )

        if not isinstance(self.status, WhatsAppCloudConnectionStatus):
            raise TypeError("status must be a WhatsAppCloudConnectionStatus")
        if not isinstance(self.webhook_subscription_status, WebhookSubscriptionStatus):
            raise TypeError("webhook_subscription_status must be a WebhookSubscriptionStatus")

        object.__setattr__(self, "capabilities", _validate_capabilities(self.capabilities))
        object.__setattr__(
            self,
            "webhook_public_key",
            _validate_webhook_public_key(self.webhook_public_key),
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
        if self.last_verified_at is not None:
            object.__setattr__(
                self,
                "last_verified_at",
                _validate_timezone_aware_datetime(self.last_verified_at, "last_verified_at"),
            )
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")

        object.__setattr__(self, "version", _validate_version(self.version))

        if connection_requires_credentials(self.status) and (
            self.access_token_ref is None
            or self.app_secret_ref is None
            or self.verify_token_ref is None
        ):
            raise WhatsAppCloudConnectionError(
                "active connections require all credential references"
            )

    def __repr__(self) -> str:
        return (
            "WhatsAppCloudConnection("
            f"id={self.id!s}, "
            f"tenant_id={self.tenant_id!s}, "
            f"status={self.status.value!r}, "
            f"version={self.version}"
            ")"
        )


__all__ = [
    "WebhookSubscriptionStatus",
    "WhatsAppCloudConnection",
    "WhatsAppCloudConnectionError",
    "WhatsAppCloudConnectionStatus",
    "connection_allows_ingestion",
    "connection_allows_outbound",
    "connection_requires_credentials",
]
