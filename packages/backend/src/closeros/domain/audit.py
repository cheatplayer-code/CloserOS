"""Framework-independent immutable audit domain model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_METADATA_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_METADATA_STRING_LENGTH = 128
_MAX_METADATA_INTEGER = 1_000_000
_MIN_METADATA_INTEGER = 0

_SENSITIVE_KEY_FRAGMENTS: frozenset[str] = frozenset(
    {
        "password",
        "token",
        "secret",
        "email",
        "phone",
        "name",
        "cookie",
        "authorization",
        "body",
        "content",
        "message",
        "prompt",
        "document",
    }
)

_ALLOWED_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "outcome",
        "reason_code",
        "assurance_level",
        "session_stage",
        "mfa_method",
        "status",
        "error_class",
        "http_method",
        "http_status",
        "route_template",
        "source",
        "affected_count",
        "previous_status",
        "new_status",
    }
)


class AuditActorType(StrEnum):
    ANONYMOUS = "anonymous"
    USER = "user"
    SYSTEM = "system"
    SERVICE = "service"


class AuditScope(StrEnum):
    GLOBAL = "global"
    TENANT = "tenant"


class AuditAction(StrEnum):
    USER_REGISTRATION_COMPLETED = "user.registration.completed"
    USER_EMAIL_VERIFICATION_REQUESTED = "user.email_verification.requested"
    USER_EMAIL_VERIFICATION_COMPLETED = "user.email_verification.completed"
    AUTH_LOGIN_SUCCEEDED = "auth.login.succeeded"
    AUTH_LOGIN_FAILED = "auth.login.failed"
    AUTH_MFA_COMPLETED = "auth.mfa.completed"
    AUTH_MFA_FAILED = "auth.mfa.failed"
    AUTH_SESSION_REVOKED = "auth.session.revoked"
    AUTH_SESSION_REVOKED_ALL = "auth.session.revoked_all"
    AUTH_PASSWORD_RESET_REQUESTED = "auth.password_reset.requested"
    AUTH_PASSWORD_RESET_COMPLETED = "auth.password_reset.completed"
    AUTH_PASSWORD_CHANGED = "auth.password.changed"
    TENANT_ACCESS_GRANTED = "tenant.access.granted"
    TENANT_ACCESS_DENIED = "tenant.access.denied"
    AUDIT_LOG_VIEWED = "audit.log_viewed"


class AuditTargetType(StrEnum):
    USER = "user"
    CREDENTIAL = "credential"
    SESSION = "session"
    TENANT = "tenant"
    AUDIT_LOG = "audit_log"
    AUTHENTICATION = "authentication"


class AuditMetadataError(ValueError):
    """Raised when audit metadata violates the safe metadata policy."""


class AuditInvariantError(ValueError):
    """Raised when an audit event violates domain invariants."""


MetadataScalar = str | int | bool


def _validate_metadata_key(key: object) -> str:
    if not isinstance(key, str):
        raise AuditMetadataError("metadata keys must be strings")

    normalized = key.strip().lower()
    if normalized != key:
        raise AuditMetadataError("metadata keys must already be normalized")

    if not _METADATA_KEY_PATTERN.fullmatch(normalized):
        raise AuditMetadataError("metadata key format is invalid")

    if normalized not in _ALLOWED_METADATA_KEYS:
        raise AuditMetadataError("metadata key is not allowlisted")

    for fragment in _SENSITIVE_KEY_FRAGMENTS:
        if fragment in normalized:
            raise AuditMetadataError("metadata key contains a sensitive fragment")

    return normalized


def _validate_metadata_value(value: object) -> MetadataScalar:
    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        if not _MIN_METADATA_INTEGER <= value <= _MAX_METADATA_INTEGER:
            raise AuditMetadataError("metadata integer is out of bounds")
        return value

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise AuditMetadataError("metadata string values must not be empty")
        if normalized != value:
            raise AuditMetadataError("metadata string values must already be normalized")
        if len(normalized) > _MAX_METADATA_STRING_LENGTH:
            raise AuditMetadataError("metadata string value is too long")
        if any(character.isspace() for character in normalized):
            raise AuditMetadataError("metadata string values must not contain whitespace")
        return normalized

    raise AuditMetadataError("metadata values must be safe scalar types")


@dataclass(frozen=True, slots=True)
class AuditMetadata:
    """Immutable, allowlisted audit metadata with deterministic ordering."""

    _items: tuple[tuple[str, MetadataScalar], ...] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self._items, tuple):
            raise TypeError("_items must be a tuple")

        seen: set[str] = set()
        for key, value in self._items:
            validated_key = _validate_metadata_key(key)
            if validated_key in seen:
                raise AuditMetadataError("metadata keys must be unique")
            seen.add(validated_key)
            _validate_metadata_value(value)

        if tuple(item[0] for item in self._items) != tuple(sorted(seen)):
            raise AuditMetadataError("metadata items must be sorted by key")

    @classmethod
    def empty(cls) -> AuditMetadata:
        return cls(_items=())

    @classmethod
    def from_mapping(cls, values: dict[str, MetadataScalar]) -> AuditMetadata:
        if not isinstance(values, dict):
            raise TypeError("values must be a dict")

        normalized_items = tuple(
            (_validate_metadata_key(key), _validate_metadata_value(value))
            for key, value in sorted(values.items(), key=lambda item: item[0])
        )
        return cls(_items=normalized_items)

    def to_mapping(self) -> dict[str, MetadataScalar]:
        return dict(self._items)

    def get(self, key: str) -> MetadataScalar | None:
        for item_key, value in self._items:
            if item_key == key:
                return value
        return None

    def __len__(self) -> int:
        return len(self._items)


@dataclass(frozen=True, slots=True)
class AuditActor:
    actor_type: AuditActorType
    actor_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.actor_type, AuditActorType):
            raise TypeError("actor_type must be an AuditActorType")

        if self.actor_type is AuditActorType.ANONYMOUS and self.actor_id is not None:
            raise AuditInvariantError("anonymous actors cannot have actor IDs")

        if self.actor_type is AuditActorType.USER and self.actor_id is None:
            raise AuditInvariantError("user actors require actor IDs")

        if self.actor_type is AuditActorType.SYSTEM and self.actor_id is not None:
            raise AuditInvariantError("system actors cannot have actor IDs")

        if self.actor_type is AuditActorType.SERVICE and self.actor_id is None:
            raise AuditInvariantError("service actors require actor IDs")

        if self.actor_id is not None and not isinstance(self.actor_id, UUID):
            raise TypeError("actor_id must be a UUID when present")


@dataclass(frozen=True, slots=True)
class AuditTarget:
    target_type: AuditTargetType
    target_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target_type, AuditTargetType):
            raise TypeError("target_type must be an AuditTargetType")

        if self.target_id is not None and not isinstance(self.target_id, UUID):
            raise TypeError("target_id must be a UUID when present")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: UUID
    scope: AuditScope
    tenant_id: UUID | None
    actor: AuditActor
    action: AuditAction
    target: AuditTarget
    occurred_at: datetime
    correlation_id: UUID
    metadata: AuditMetadata

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID")

        if not isinstance(self.scope, AuditScope):
            raise TypeError("scope must be an AuditScope")

        if self.scope is AuditScope.TENANT and self.tenant_id is None:
            raise AuditInvariantError("tenant scope requires tenant_id")

        if self.scope is AuditScope.GLOBAL and self.tenant_id is not None:
            raise AuditInvariantError("global scope requires tenant_id to be absent")

        if self.tenant_id is not None and not isinstance(self.tenant_id, UUID):
            raise TypeError("tenant_id must be a UUID when present")

        if not isinstance(self.actor, AuditActor):
            raise TypeError("actor must be an AuditActor")

        if not isinstance(self.action, AuditAction):
            raise TypeError("action must be an AuditAction")

        if not isinstance(self.target, AuditTarget):
            raise TypeError("target must be an AuditTarget")

        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime")

        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise AuditInvariantError("occurred_at must be timezone-aware")

        if not isinstance(self.correlation_id, UUID):
            raise TypeError("correlation_id must be a UUID")

        if not isinstance(self.metadata, AuditMetadata):
            raise TypeError("metadata must be AuditMetadata")

    def __repr__(self) -> str:
        return (
            "AuditEvent("
            f"id={self.id!s}, "
            f"scope={self.scope.value!r}, "
            f"action={self.action.value!r}, "
            f"target_type={self.target.target_type.value!r}, "
            f"metadata_keys={len(self.metadata)}"
            ")"
        )


def build_audit_event(
    *,
    event_id: UUID,
    scope: AuditScope,
    tenant_id: UUID | None,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    action: AuditAction,
    target_type: AuditTargetType,
    target_id: UUID | None,
    occurred_at: datetime,
    correlation_id: UUID,
    metadata: AuditMetadata | dict[str, MetadataScalar] | None = None,
) -> AuditEvent:
    resolved_metadata = (
        metadata
        if isinstance(metadata, AuditMetadata)
        else AuditMetadata.empty()
        if metadata is None
        else AuditMetadata.from_mapping(metadata)
    )
    return AuditEvent(
        id=event_id,
        scope=scope,
        tenant_id=tenant_id,
        actor=AuditActor(actor_type=actor_type, actor_id=actor_id),
        action=action,
        target=AuditTarget(target_type=target_type, target_id=target_id),
        occurred_at=occurred_at,
        correlation_id=correlation_id,
        metadata=resolved_metadata,
    )


__all__ = [
    "AuditAction",
    "AuditActor",
    "AuditActorType",
    "AuditEvent",
    "AuditInvariantError",
    "AuditMetadata",
    "AuditMetadataError",
    "AuditScope",
    "AuditTarget",
    "AuditTargetType",
    "MetadataScalar",
    "build_audit_event",
]
