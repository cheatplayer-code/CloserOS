"""Unit tests for tenant metrics API routes and schemas."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from closeros.application.authentication_workflows import (
    AuthenticationWorkflowService,
    ResolvedAuthenticationSession,
)
from closeros.application.metrics_enqueue_service import MetricsEnqueueUnavailableError
from closeros.application.tenant_context import TenantContext
from closeros.domain.authentication import (
    AuthenticationAssuranceLevel,
    AuthenticationSessionStage,
    AuthenticationTokenHash,
)
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.identity import MembershipStatus, Role, TenantStatus, UserStatus
from closeros.domain.membership import Membership
from closeros.domain.metrics import (
    METRIC_FORMULA_VERSION,
    MetricKey,
    MetricScope,
    MetricSnapshot,
    MetricSnapshotStatus,
    MetricValue,
    MetricWindow,
)
from closeros.domain.retention import RetentionPolicy
from closeros.domain.tenant import Tenant
from closeros.domain.user import User
from closeros.security.authentication_tokens import RawAuthenticationToken
from closeros_api.app import create_app
from closeros_api.auth_ports import CaptureNotificationDispatcher, InMemoryRateLimiter
from closeros_api.auth_security import CSRF_HEADER_NAME, generate_csrf_token
from closeros_api.composition import ApiRuntimeOverrides
from closeros_api.metrics_schemas import MetricsListResponse, MetricsRecalculateAcceptedResponse
from fastapi.testclient import TestClient

from tests.auth_api_support import (
    TEST_CSRF_SECRET,
    TEST_ORIGIN,
    TOKEN_ENTROPY_A,
    FixedClock,
    deterministic_token_string,
    development_api_settings,
)


def _workflows(service: object) -> AuthenticationWorkflowService:
    return cast(AuthenticationWorkflowService, service)


def _valid_retention_policy() -> RetentionPolicy:
    return RetentionPolicy(
        raw_message_days=30,
        sanitized_message_days=30,
        ai_output_days=30,
        audit_log_days=365,
        backup_days=30,
        post_contract_deletion_days=90,
    )


def _tenant_context(*, roles: frozenset[Role]) -> TenantContext:
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    user_id = UUID("00000000-0000-0000-0000-000000000010")
    return TenantContext(
        tenant=Tenant(
            id=tenant_id,
            name="Acme",
            status=TenantStatus.ACTIVE,
            time_zone="Asia/Almaty",
            retention_policy=_valid_retention_policy(),
        ),
        user=User(id=user_id, status=UserStatus.ACTIVE),
        membership=Membership(
            id=UUID("00000000-0000-0000-0000-000000000500"),
            tenant_id=tenant_id,
            user_id=user_id,
            roles=roles,
            status=MembershipStatus.ACTIVE,
        ),
        correlation_id=UUID("00000000-0000-0000-0000-000000000400"),
    )


def _resolved_session(*, user_id: UUID, now: datetime) -> ResolvedAuthenticationSession:
    return ResolvedAuthenticationSession(
        session=AuthenticationSession(
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
        ),
        user=User(id=user_id, status=UserStatus.ACTIVE),
    )


class FakeMetricsQueryService:
    async def list_snapshots(self, **kwargs: object) -> tuple[MetricSnapshot, ...]:
        window_start = datetime(2026, 7, 12, 0, 0, tzinfo=UTC)
        window_end = datetime(2026, 7, 13, 0, 0, tzinfo=UTC)
        return (
            MetricSnapshot(
                id=UUID("00000000-0000-0000-0000-000000000600"),
                tenant_id=UUID("00000000-0000-0000-0000-000000000300"),
                scope=MetricScope.TENANT,
                manager_user_id=None,
                window=MetricWindow(
                    start=window_start,
                    end=window_end,
                    window_code="day_2026_07_12",
                ),
                formula_version=METRIC_FORMULA_VERSION,
                source_watermark=window_end,
                computed_at=window_end,
                status=MetricSnapshotStatus.COMPLETED,
                values=(MetricValue(key=MetricKey.INBOUND_MESSAGE_COUNT, value=3),),
            ),
        )


class FakeMetricsEnqueueService:
    async def enqueue_tenant_recalculation(self, **kwargs: object) -> UUID:
        return uuid4()


class RecordingMetricsEnqueueService(FakeMetricsEnqueueService):
    def __init__(self) -> None:
        self.calls = 0

    async def enqueue_tenant_recalculation(self, **kwargs: object) -> UUID:
        self.calls += 1
        return await super().enqueue_tenant_recalculation(**kwargs)


SESSION_TOKEN = RawAuthenticationToken(deterministic_token_string(TOKEN_ENTROPY_A))


def _authenticated_headers() -> dict[str, str]:
    return {
        "Origin": TEST_ORIGIN,
        CSRF_HEADER_NAME: generate_csrf_token(
            session_token=SESSION_TOKEN,
            secret=TEST_CSRF_SECRET,
        ),
    }


def _build_app(
    *,
    roles: frozenset[Role],
    metrics_query_service: FakeMetricsQueryService | None = None,
    metrics_enqueue_service: FakeMetricsEnqueueService | None = None,
) -> TestClient:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    context = _tenant_context(roles=roles)
    now = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)

    class FakeContextResolver:
        async def resolve(self, **kwargs: object) -> TenantContext:
            return context

    class FakeWorkflows:
        async def resolve_session(self, **kwargs: object) -> ResolvedAuthenticationSession:
            return _resolved_session(user_id=context.user.id, now=now)

    app = create_app(
        settings=settings,
        overrides=ApiRuntimeOverrides(
            workflow_service=_workflows(FakeWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
            tenant_context_resolver=cast(Any, FakeContextResolver()),
            metrics_query_service=cast(Any, metrics_query_service or FakeMetricsQueryService()),
            metrics_enqueue_service=cast(
                Any,
                metrics_enqueue_service or FakeMetricsEnqueueService(),
            ),
            clock=FixedClock(now),
            engine=None,
            session_factory=None,
            uow_factory=lambda: (_ for _ in ()).throw(RuntimeError("unused")),
        ),
    )
    return TestClient(app, base_url="http://testserver")


def test_metrics_modules_do_not_import_forbidden_libraries() -> None:
    forbidden = ("psycopg", "sqlalchemy")
    api_dir = Path("apps/api/src/closeros_api")
    for path in api_dir.glob("metrics*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not any(name.startswith(forbidden) for name in imports)


def test_list_metrics_requires_authenticated_session() -> None:
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

    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/tenants/{tenant_id}/metrics",
            params={"scope": "tenant"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication failed"


def test_list_metrics_denies_non_privileged_role() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    client = _build_app(roles=frozenset({Role.MANAGER}))
    client.cookies.set("closeros_dev_session", SESSION_TOKEN.value)
    response = client.get(
        f"/api/v1/tenants/{tenant_id}/metrics",
        params={"scope": "tenant"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "access denied"


@pytest.mark.parametrize(
    "role",
    [Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN],
)
def test_list_metrics_allows_privileged_roles(role: Role) -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    client = _build_app(roles=frozenset({role}))
    client.cookies.set("closeros_dev_session", SESSION_TOKEN.value)
    response = client.get(
        f"/api/v1/tenants/{tenant_id}/metrics",
        params={"scope": "tenant"},
    )

    assert response.status_code == 200
    payload = MetricsListResponse.model_validate(response.json())
    assert len(payload.snapshots) == 1
    assert payload.snapshots[0].values[0].key == "inbound_message_count"


def test_recalculate_metrics_requires_authenticated_session() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    client = _build_app(roles=frozenset({Role.OWNER}))
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/metrics/recalculate",
        headers={"Origin": TEST_ORIGIN},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication failed"


def test_recalculate_metrics_requires_csrf() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    client = _build_app(roles=frozenset({Role.OWNER}))
    client.cookies.set("closeros_dev_session", SESSION_TOKEN.value)
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/metrics/recalculate",
        headers={"Origin": TEST_ORIGIN},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "access denied"


def test_recalculate_metrics_denies_non_privileged_role() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    client = _build_app(roles=frozenset({Role.ANALYST}))
    client.cookies.set("closeros_dev_session", SESSION_TOKEN.value)
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/metrics/recalculate",
        headers=_authenticated_headers(),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "access denied"


@pytest.mark.parametrize(
    "role",
    [Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN],
)
def test_recalculate_metrics_accepts_privileged_role_with_csrf(role: Role) -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    enqueue = RecordingMetricsEnqueueService()
    client = _build_app(
        roles=frozenset({role}),
        metrics_enqueue_service=enqueue,
    )
    client.cookies.set("closeros_dev_session", SESSION_TOKEN.value)
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/metrics/recalculate",
        headers=_authenticated_headers(),
    )

    assert response.status_code == 202
    payload = MetricsRecalculateAcceptedResponse.model_validate(response.json())
    assert payload.message == "accepted"
    assert enqueue.calls == 1


def test_recalculate_metrics_returns_unavailable_when_enqueue_fails() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")

    class FailingEnqueueService:
        async def enqueue_tenant_recalculation(self, **kwargs: object) -> UUID:
            raise MetricsEnqueueUnavailableError("queue unavailable")

    client = _build_app(
        roles=frozenset({Role.OWNER}),
        metrics_enqueue_service=cast(Any, FailingEnqueueService()),
    )
    client.cookies.set("closeros_dev_session", SESSION_TOKEN.value)
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/metrics/recalculate",
        headers=_authenticated_headers(),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "request unavailable"
