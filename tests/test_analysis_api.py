"""API contract tests for analysis endpoints (currently not exposed)."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from closeros.application.authentication_workflows import AuthenticationWorkflowService
from closeros_api.app import create_app
from closeros_api.auth_ports import CaptureNotificationDispatcher, InMemoryRateLimiter
from closeros_api.composition import ApiRuntimeOverrides
from fastapi.testclient import TestClient

from tests.auth_api_support import development_api_settings


def _workflows(service: object) -> AuthenticationWorkflowService:
    return cast(AuthenticationWorkflowService, service)


def _client() -> TestClient:
    settings = development_api_settings(
        database_url="postgresql://user:synthetic@127.0.0.1:5432/closeros_local"
    )

    class FakeWorkflows:
        async def resolve_session(self, **kwargs: object) -> object:
            raise RuntimeError("unused")

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
    return TestClient(app, base_url="http://testserver")


def test_analysis_request_endpoint_is_not_registered_yet() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    thread_id = UUID("00000000-0000-0000-0000-000000000010")
    with _client() as client:
        response = client.post(f"/api/v1/tenants/{tenant_id}/analysis/{thread_id}")
    assert response.status_code == 404


def test_analysis_list_endpoint_is_not_registered_yet() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    with _client() as client:
        response = client.get(f"/api/v1/tenants/{tenant_id}/analysis")
    assert response.status_code == 404
