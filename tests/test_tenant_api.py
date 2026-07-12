"""Unit tests for tenant API routes and schemas."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.application.audit_queries import TenantAuditQueryService
from closeros.application.authentication_workflows import (
    AuthenticationWorkflowService,
    ResolvedAuthenticationSession,
)
from closeros.application.tenant_context import TenantContext
from closeros.domain.audit import (
    AuditAction,
    AuditActorType,
    AuditMetadata,
    AuditScope,
    AuditTargetType,
    build_audit_event,
)
from closeros.domain.identity import MembershipStatus, Role, TenantStatus, UserStatus
from closeros.domain.membership import Membership
from closeros.domain.retention import RetentionPolicy
from closeros.domain.tenant import Tenant
from closeros.domain.user import User
from closeros_api.app import create_app
from closeros_api.auth_ports import CaptureNotificationDispatcher, InMemoryRateLimiter
from closeros_api.composition import ApiRuntimeOverrides
from closeros_api.tenant_schemas import AuditEventResponse, TenantSummaryResponse
from fastapi.testclient import TestClient

from tests.auth_api_support import (
    TOKEN_ENTROPY_A,
    deterministic_token_string,
    development_api_settings,
)


def _workflows(service: object) -> AuthenticationWorkflowService:
    return cast(AuthenticationWorkflowService, service)


def test_tenant_modules_do_not_import_forbidden_libraries() -> None:
    forbidden = ("psycopg", "sqlalchemy")
    api_dir = Path("apps/api/src/closeros_api")
    for path in api_dir.glob("tenant*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not any(name.startswith(forbidden) for name in imports)


def test_list_tenants_requires_authenticated_session() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )

    class FakeWorkflows:
        async def resolve_session(self, **kwargs: object) -> object:
            raise AssertionError("resolve_session should not be called without a cookie")

    app = create_app(
        settings=settings,
        overrides=ApiRuntimeOverrides(
            workflow_service=_workflows(FakeWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
            engine=None,
            session_factory=None,
            uow_factory=lambda: (_ for _ in ()).throw(RuntimeError("unused")),
        ),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants")

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication failed"


def test_audit_event_response_omits_metadata() -> None:
    now = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    event = build_audit_event(
        event_id=UUID("00000000-0000-0000-0000-000000000200"),
        scope=AuditScope.TENANT,
        tenant_id=UUID("00000000-0000-0000-0000-000000000300"),
        actor_type=AuditActorType.USER,
        actor_id=UUID("00000000-0000-0000-0000-000000000010"),
        action=AuditAction.AUTH_LOGIN_SUCCEEDED,
        target_type=AuditTargetType.AUTHENTICATION,
        target_id=None,
        occurred_at=now,
        correlation_id=UUID("00000000-0000-0000-0000-000000000400"),
        metadata=AuditMetadata.from_mapping({"outcome": "success"}),
    )

    payload = AuditEventResponse(
        id=event.id,
        scope=event.scope.value,
        tenant_id=event.tenant_id,
        actor_type=event.actor.actor_type.value,
        actor_id=event.actor.actor_id,
        action=event.action.value,
        target_type=event.target.target_type.value,
        target_id=event.target.target_id,
        occurred_at=event.occurred_at,
        correlation_id=event.correlation_id,
    )

    dumped = payload.model_dump()
    assert "metadata" not in dumped
    assert dumped["action"] == "auth.login.succeeded"


def _valid_retention_policy() -> RetentionPolicy:
    return RetentionPolicy(
        raw_message_days=30,
        sanitized_message_days=30,
        ai_output_days=30,
        audit_log_days=365,
        backup_days=30,
        post_contract_deletion_days=90,
    )


def test_list_tenant_audit_events_denies_non_privileged_role() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    user_id = UUID("00000000-0000-0000-0000-000000000010")
    now = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    tenant = Tenant(
        id=tenant_id,
        name="Acme",
        status=TenantStatus.ACTIVE,
        time_zone="UTC",
        retention_policy=_valid_retention_policy(),
    )
    user = User(id=user_id, status=UserStatus.ACTIVE)
    membership = Membership(
        id=UUID("00000000-0000-0000-0000-000000000500"),
        tenant_id=tenant_id,
        user_id=user_id,
        roles=frozenset({Role.MANAGER}),
        status=MembershipStatus.ACTIVE,
    )

    class FakeContextResolver:
        async def resolve(self, **kwargs: object) -> TenantContext:
            return TenantContext(
                tenant=tenant,
                user=user,
                membership=membership,
                correlation_id=UUID("00000000-0000-0000-0000-000000000400"),
            )

    class FakeWorkflows:
        async def resolve_session(self, **kwargs: object) -> ResolvedAuthenticationSession:
            from closeros.domain.authentication import (
                AuthenticationAssuranceLevel,
                AuthenticationSessionStage,
                AuthenticationTokenHash,
            )
            from closeros.domain.authentication_session import AuthenticationSession

            session = AuthenticationSession(
                id=UUID("00000000-0000-0000-0000-000000000100"),
                user_id=user_id,
                token_hash=AuthenticationTokenHash(digest=bytes(range(32))),
                stage=AuthenticationSessionStage.AUTHENTICATED,
                assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
                mfa_completed=False,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(hours=12),
                revoked_at=None,
            )
            return ResolvedAuthenticationSession(session=session, user=user)

    app = create_app(
        settings=settings,
        overrides=ApiRuntimeOverrides(
            workflow_service=_workflows(FakeWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
            tenant_context_resolver=cast(Any, FakeContextResolver()),
            tenant_audit_query_service=TenantAuditQueryService(
                audit_uow_factory=lambda: (_ for _ in ()).throw(RuntimeError("unused")),
            ),
            engine=None,
            session_factory=None,
            uow_factory=lambda: (_ for _ in ()).throw(RuntimeError("unused")),
        ),
    )

    raw_token = deterministic_token_string(TOKEN_ENTROPY_A)
    with TestClient(app, base_url="http://testserver") as client:
        client.cookies.set("closeros_dev_session", raw_token)
        response = client.get(f"/api/v1/tenants/{tenant_id}/audit-events")

    assert response.status_code == 403
    assert response.json()["detail"] == "tenant access denied"


def test_tenant_summary_response_includes_roles() -> None:
    payload = TenantSummaryResponse(
        id=UUID("00000000-0000-0000-0000-000000000300"),
        name="Acme",
        status="active",
        time_zone="UTC",
        roles=["manager", "owner"],
    )

    assert payload.roles == ["manager", "owner"]


def test_tenant_summary_response_rejects_empty_roles() -> None:
    with pytest.raises(ValueError):
        TenantSummaryResponse(
            id=UUID("00000000-0000-0000-0000-000000000300"),
            name="Acme",
            status="active",
            time_zone="UTC",
            roles=[],
        )


def test_tenant_modules_do_not_import_canonical_orm() -> None:
    forbidden = ("canonical_orm", "canonical_repositories")
    api_dir = Path("apps/api/src/closeros_api")
    for path in api_dir.glob("tenant*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not any(name.endswith(fragment) for name in imports for fragment in forbidden)
