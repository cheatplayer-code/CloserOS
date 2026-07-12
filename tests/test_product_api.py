"""Unit tests for RSTU product workspace API routes."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from closeros.application.authentication_workflows import (
    AuthenticationWorkflowService,
    ResolvedAuthenticationSession,
)
from closeros.application.dashboard_query_service import DashboardMetricValue, DashboardSummary
from closeros.application.tenant_context import TenantContext
from closeros.domain.access import TenantAccessDeniedError
from closeros.domain.authentication import (
    AuthenticationAssuranceLevel,
    AuthenticationSessionStage,
    AuthenticationTokenHash,
)
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.follow_up_task import FollowUpTask, FollowUpTaskPriority, FollowUpTaskStatus
from closeros.domain.identity import MembershipStatus, Role, TenantStatus, UserStatus
from closeros.domain.membership import Membership
from closeros.domain.product_metrics import DASHBOARD_FORMULA_VERSION
from closeros.domain.retention import RetentionPolicy
from closeros.domain.tenant import Tenant
from closeros.domain.user import User
from closeros.security.authentication_tokens import RawAuthenticationToken
from closeros_api.app import create_app
from closeros_api.auth_ports import CaptureNotificationDispatcher, InMemoryRateLimiter
from closeros_api.auth_security import CSRF_HEADER_NAME, generate_csrf_token
from closeros_api.composition import ApiRuntimeOverrides
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


SESSION_TOKEN = RawAuthenticationToken(deterministic_token_string(TOKEN_ENTROPY_A))


def _authenticated_headers() -> dict[str, str]:
    return {
        "Origin": TEST_ORIGIN,
        CSRF_HEADER_NAME: generate_csrf_token(
            session_token=SESSION_TOKEN,
            secret=TEST_CSRF_SECRET,
        ),
    }


class FakeDashboardQueryService:
    async def get_dashboard(self, **kwargs: object) -> DashboardSummary:
        window_start = datetime(2026, 7, 12, 0, 0, tzinfo=UTC)
        window_end = datetime(2026, 7, 13, 0, 0, tzinfo=UTC)
        return DashboardSummary(
            formula_version=DASHBOARD_FORMULA_VERSION,
            window_start=window_start,
            window_end=window_end,
            previous_window_start=window_start - timedelta(days=1),
            previous_window_end=window_start,
            total_conversations=5,
            open_high_severity_findings=1,
            overdue_follow_up_tasks=2,
            metrics=(
                DashboardMetricValue(
                    key="active_thread_count",
                    current_value=5,
                    previous_value=4,
                    delta=1,
                ),
            ),
            manager_summaries=(),
        )


class FakeScorecardQueryService:
    async def list_manager_scorecards(self, **kwargs: object) -> tuple[object, ...]:
        return ()

    async def get_scorecard(self, **kwargs: object) -> object | None:
        return None


class FakeConversationQueryService:
    async def list_conversations(self, **kwargs: object) -> object:
        return type("Page", (), {"items": (), "next_cursor": None})()

    async def get_conversation_detail(self, **kwargs: object) -> object | None:
        return None


class FakeFollowUpTaskService:
    async def list_tasks(self, **kwargs: object) -> object:
        return type("Page", (), {"items": (), "next_cursor": None})()

    async def get_task(self, **kwargs: object) -> object | None:
        return None

    async def create_task(self, **kwargs: object) -> object:
        raise AssertionError("not implemented in fake")

    async def mutate_status(self, **kwargs: object) -> object:
        raise AssertionError("not implemented in fake")


class RecordingFollowUpTaskService(FakeFollowUpTaskService):
    async def create_task(self, **kwargs: object) -> FollowUpTask:
        now = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
        return FollowUpTask(
            id=UUID("00000000-0000-0000-0000-000000000701"),
            tenant_id=UUID("00000000-0000-0000-0000-000000000300"),
            conversation_thread_id=UUID(str(kwargs["conversation_thread_id"])),
            source_finding_id=None,
            title=str(kwargs["title"]),
            status=FollowUpTaskStatus.OPEN,
            priority=FollowUpTaskPriority.NORMAL,
            assigned_membership_id=None,
            created_by_user_id=UUID("00000000-0000-0000-0000-000000000010"),
            due_at=None,
            completed_at=None,
            cancelled_at=None,
            created_at=now,
            updated_at=now,
            version=1,
        )


def _build_app(*, roles: frozenset[Role], task_service: object | None = None) -> TestClient:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    context = _tenant_context(roles=roles)
    now = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)

    class FakeContextResolver:
        async def resolve(self, **kwargs: object) -> TenantContext:
            requested_tenant_id = kwargs.get("tenant_id")
            if requested_tenant_id != context.tenant.id:
                raise TenantAccessDeniedError("tenant access denied")
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
            dashboard_query_service=cast(Any, FakeDashboardQueryService()),
            scorecard_query_service=cast(Any, FakeScorecardQueryService()),
            conversation_query_service=cast(Any, FakeConversationQueryService()),
            follow_up_task_service=cast(
                Any,
                task_service or FakeFollowUpTaskService(),
            ),
            clock=FixedClock(now),
            engine=None,
            session_factory=None,
            uow_factory=lambda: (_ for _ in ()).throw(RuntimeError("unused")),
        ),
    )
    client = TestClient(app, base_url="http://testserver")
    client.cookies.set("closeros_dev_session", SESSION_TOKEN.value)
    return client


def test_dashboard_requires_authenticated_session() -> None:
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
            dashboard_query_service=cast(Any, FakeDashboardQueryService()),
            engine=None,
            session_factory=None,
            uow_factory=lambda: (_ for _ in ()).throw(RuntimeError("unused")),
        ),
    )
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/tenants/{tenant_id}/dashboard",
            params={
                "window_start": "2026-07-12T00:00:00+00:00",
                "window_end": "2026-07-13T00:00:00+00:00",
            },
        )
    assert response.status_code == 401
    assert response.json()["detail"] == "authentication failed"


def test_dashboard_denies_manager_role() -> None:
    client = _build_app(roles=frozenset({Role.MANAGER}))
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    response = client.get(
        f"/api/v1/tenants/{tenant_id}/dashboard",
        params={
            "window_start": "2026-07-12T00:00:00+00:00",
            "window_end": "2026-07-13T00:00:00+00:00",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "access denied"


def test_dashboard_returns_summary_for_owner() -> None:
    client = _build_app(roles=frozenset({Role.OWNER}))
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    response = client.get(
        f"/api/v1/tenants/{tenant_id}/dashboard",
        params={
            "window_start": "2026-07-12T00:00:00+00:00",
            "window_end": "2026-07-13T00:00:00+00:00",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["formula_version"] == DASHBOARD_FORMULA_VERSION
    assert body["total_conversations"] == 5


def test_tasks_create_requires_csrf_and_origin() -> None:
    client = _build_app(roles=frozenset({Role.OWNER}))
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/tasks",
        json={
            "conversation_thread_id": str(uuid4()),
            "title": "Call back lead",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "access denied"


def test_tasks_create_with_csrf_returns_created_task() -> None:
    client = _build_app(
        roles=frozenset({Role.OWNER}),
        task_service=RecordingFollowUpTaskService(),
    )
    tenant_id = UUID("00000000-0000-0000-0000-000000000300")
    thread_id = uuid4()
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/tasks",
        headers=_authenticated_headers(),
        json={
            "conversation_thread_id": str(thread_id),
            "title": "Call back lead",
        },
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Call back lead"
    assert response.json()["status"] == "open"


def test_cross_tenant_dashboard_denied() -> None:
    client = _build_app(roles=frozenset({Role.OWNER}))
    other_tenant = UUID("00000000-0000-0000-0000-000000009999")
    response = client.get(
        f"/api/v1/tenants/{other_tenant}/dashboard",
        params={
            "window_start": "2026-07-12T00:00:00+00:00",
            "window_end": "2026-07-13T00:00:00+00:00",
        },
    )
    assert response.status_code == 403
