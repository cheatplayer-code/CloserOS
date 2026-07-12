"""Unit tests for the immutable audit domain model."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest
from closeros.domain.audit import (
    AuditAction,
    AuditActor,
    AuditActorType,
    AuditEvent,
    AuditInvariantError,
    AuditMetadata,
    AuditMetadataError,
    AuditScope,
    AuditTargetType,
    build_audit_event,
)

NOW = datetime(2026, 7, 12, 9, 0, 0, tzinfo=UTC)
EVENT_ID = UUID("00000000-0000-0000-0000-000000000001")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000010")
USER_ID = UUID("00000000-0000-0000-0000-000000000020")
TARGET_ID = UUID("00000000-0000-0000-0000-000000000030")
CORRELATION_ID = UUID("00000000-0000-0000-0000-000000000999")


def _event(
    *,
    scope: AuditScope = AuditScope.GLOBAL,
    tenant_id: UUID | None = None,
    actor_type: AuditActorType = AuditActorType.USER,
    actor_id: UUID | None = USER_ID,
    action: AuditAction = AuditAction.AUTH_LOGIN_SUCCEEDED,
    target_type: AuditTargetType = AuditTargetType.SESSION,
    target_id: UUID | None = TARGET_ID,
    occurred_at: datetime = NOW,
    metadata: dict[str, str | int | bool] | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=EVENT_ID,
        scope=scope,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        occurred_at=occurred_at,
        correlation_id=CORRELATION_ID,
        metadata=metadata or {"outcome": "success"},
    )


def test_tenant_scope_requires_tenant_id() -> None:
    with pytest.raises(AuditInvariantError):
        _event(scope=AuditScope.TENANT, tenant_id=None)


def test_global_scope_rejects_tenant_id() -> None:
    with pytest.raises(AuditInvariantError):
        _event(scope=AuditScope.GLOBAL, tenant_id=TENANT_ID)


def test_anonymous_actor_cannot_have_actor_id() -> None:
    with pytest.raises(AuditInvariantError):
        AuditActor(actor_type=AuditActorType.ANONYMOUS, actor_id=USER_ID)


def test_user_actor_requires_actor_id() -> None:
    with pytest.raises(AuditInvariantError):
        AuditActor(actor_type=AuditActorType.USER, actor_id=None)


def test_system_actor_cannot_have_actor_id() -> None:
    with pytest.raises(AuditInvariantError):
        AuditActor(actor_type=AuditActorType.SYSTEM, actor_id=USER_ID)


def test_service_actor_requires_actor_id() -> None:
    with pytest.raises(AuditInvariantError):
        AuditActor(actor_type=AuditActorType.SERVICE, actor_id=None)


def test_metadata_rejects_unknown_keys() -> None:
    with pytest.raises(AuditMetadataError):
        AuditMetadata.from_mapping({"unknown_key": "value"})


def test_metadata_rejects_sensitive_key_fragments() -> None:
    with pytest.raises(AuditMetadataError):
        AuditMetadata.from_mapping({"user_email": "x"})


def test_metadata_rejects_nested_values() -> None:
    with pytest.raises(AuditMetadataError):
        AuditMetadata.from_mapping({"outcome": {"nested": True}})  # type: ignore[dict-item]


def test_metadata_rejects_long_strings() -> None:
    with pytest.raises(AuditMetadataError):
        AuditMetadata.from_mapping({"outcome": "x" * 129})


def test_metadata_serializes_deterministically() -> None:
    first = AuditMetadata.from_mapping({"status": "active", "outcome": "success"})
    second = AuditMetadata.from_mapping({"outcome": "success", "status": "active"})
    assert first.to_mapping() == second.to_mapping()
    assert list(first.to_mapping()) == ["outcome", "status"]


def test_audit_event_is_deeply_immutable() -> None:
    event = _event()
    with pytest.raises(FrozenInstanceError):
        event.action = AuditAction.AUTH_LOGIN_FAILED  # type: ignore[misc]


def test_audit_metadata_is_immutable() -> None:
    metadata = AuditMetadata.from_mapping({"outcome": "success"})
    with pytest.raises(FrozenInstanceError):
        metadata._items = ()  # type: ignore[misc]


def test_audit_event_repr_hides_metadata_values() -> None:
    event = _event(metadata={"reason_code": "invalid_credentials"})
    rendered = repr(event)
    assert "invalid_credentials" not in rendered
    assert "auth.login.succeeded" in rendered


def test_occurred_at_must_be_timezone_aware() -> None:
    naive = datetime(2026, 7, 12, 9, 0, 0)
    with pytest.raises(AuditInvariantError):
        _event(occurred_at=naive)


def test_controlled_action_taxonomy_contains_required_entries() -> None:
    required = {
        "user.registration.completed",
        "auth.login.failed",
        "audit.log_viewed",
        "tenant.access.denied",
    }
    values = {action.value for action in AuditAction}
    assert required.issubset(values)


def test_target_type_is_always_present() -> None:
    event = _event(target_type=AuditTargetType.AUTHENTICATION, target_id=None)
    assert event.target.target_type is AuditTargetType.AUTHENTICATION
    assert event.target.target_id is None
