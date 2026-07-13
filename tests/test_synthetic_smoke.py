"""HTTP integration tests for synthetic smoke flow."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from closeros.application.atomic_content_commands import AtomicContentCommandService
from closeros.application.bootstrap_tenant_service import BootstrapTenantService
from closeros.application.metrics_windows import (
    local_date_from_timestamp,
    rolling_30_day_window_for_local_date,
)
from closeros.application.synthetic_demo_seed_service import SyntheticDemoSeedService
from closeros.infrastructure.ops_encryption import build_ops_content_encryption_service
from closeros_api.app import create_app
from closeros_api.auth_ports import CaptureNotificationDispatcher
from closeros_api.auth_security import CSRF_HEADER_NAME
from closeros_api.composition import AuthRuntimeOverrides
from fastapi.testclient import TestClient

from tests.auth_api_support import TEST_ORIGIN, TEST_PASSWORD, development_api_settings

pytestmark = pytest.mark.z0_persistence

SMOKE_EMAIL = "smoke.owner@example.invalid"


def _build_client(auth_test_database_url: str) -> tuple[TestClient, CaptureNotificationDispatcher]:
    dispatcher = CaptureNotificationDispatcher()
    app = create_app(
        settings=development_api_settings(database_url=auth_test_database_url),
        overrides=AuthRuntimeOverrides(notification_dispatcher=dispatcher),
    )
    return TestClient(app, base_url="http://testserver"), dispatcher


def _bootstrap_and_seed(
    integrated_uow_factory: Any,
    auth_test_database_url: str,
) -> str:
    dispatcher = CaptureNotificationDispatcher()
    client = TestClient(
        create_app(
            settings=development_api_settings(database_url=auth_test_database_url),
            overrides=AuthRuntimeOverrides(notification_dispatcher=dispatcher),
        ),
        base_url="http://testserver",
    )
    register = client.post(
        "/api/v1/auth/register",
        json={"email": SMOKE_EMAIL, "password": TEST_PASSWORD},
    )
    assert register.status_code == 202
    raw_token = dispatcher.verification_deliveries[0].raw_token
    confirm = client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"verification_token": raw_token.value},
    )
    assert confirm.status_code == 204
    client.close()

    async def exercise() -> str:
        bootstrap = BootstrapTenantService(
            uow_factory=integrated_uow_factory,
            uuid_factory=uuid4,
            clock=lambda: datetime.now(UTC),
        )
        tenant = await bootstrap.bootstrap_owner_tenant(
            owner_email=SMOKE_EMAIL,
            tenant_name="Smoke Synthetic Tenant",
            time_zone="Asia/Almaty",
        )
        content_encryption = build_ops_content_encryption_service(integrated_uow_factory)
        seed = SyntheticDemoSeedService(
            uow_factory=integrated_uow_factory,
            content_encryption=content_encryption,
            atomic_commands=AtomicContentCommandService(
                uow_factory=integrated_uow_factory,
                content_encryption=content_encryption,
            ),
            service_actor_id=uuid4(),
            uuid_factory=uuid4,
            clock=lambda: datetime.now(UTC),
        )
        await seed.seed_demo(tenant_id=tenant.tenant_id)
        return str(tenant.tenant_id)

    return asyncio.run(exercise())


def test_synthetic_smoke_http_flow(
    integrated_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    tenant_id = _bootstrap_and_seed(integrated_uow_factory, auth_test_database_url)
    client, _dispatcher = _build_client(auth_test_database_url)

    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200

    login = client.post(
        "/api/v1/auth/login",
        json={"email": SMOKE_EMAIL, "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]

    tenants = client.get("/api/v1/tenants")
    assert tenants.status_code == 200
    tenant_items = tenants.json()
    assert any(str(item["id"]) == tenant_id for item in tenant_items)

    seed_now = datetime.now(tz=UTC)
    window = rolling_30_day_window_for_local_date(
        local_date=local_date_from_timestamp(occurred_at=seed_now, time_zone="Asia/Almaty"),
        time_zone="Asia/Almaty",
    )
    dashboard = client.get(
        f"/api/v1/tenants/{tenant_id}/dashboard",
        params={
            "window_start": window.start.isoformat(),
            "window_end": window.end.isoformat(),
        },
    )
    assert dashboard.status_code == 200
    assert dashboard.json()["total_conversations"] >= 1

    conversations = client.get(f"/api/v1/tenants/{tenant_id}/conversations")
    assert conversations.status_code == 200
    conversation_items = conversations.json()["conversations"]
    assert conversation_items
    thread_id = conversation_items[0]["id"]
    detail = client.get(f"/api/v1/tenants/{tenant_id}/conversations/{thread_id}")
    assert detail.status_code == 200
    analyses = detail.json()["analyses"]
    assert any(run["findings"] for run in analyses)

    managers = client.get(f"/api/v1/tenants/{tenant_id}/managers")
    assert managers.status_code == 200
    membership_id = managers.json()["managers"][0]["membership_id"]
    scorecard = client.get(
        f"/api/v1/tenants/{tenant_id}/managers/{membership_id}/scorecard",
        params={
            "window_start": window.start.isoformat(),
            "window_end": window.end.isoformat(),
        },
    )
    assert scorecard.status_code == 200

    tasks = client.get(f"/api/v1/tenants/{tenant_id}/tasks")
    assert tasks.status_code == 200
    assert tasks.json()["tasks"]

    metrics = client.get(
        f"/api/v1/tenants/{tenant_id}/metrics",
        params={
            "scope": "tenant",
            "window_start": window.start.isoformat(),
            "window_end": window.end.isoformat(),
        },
    )
    assert metrics.status_code == 200

    anonymous = TestClient(
        create_app(settings=development_api_settings(database_url=auth_test_database_url))
    )
    try:
        protected = anonymous.get(
            f"/api/v1/tenants/{tenant_id}/dashboard",
            params={
                "window_start": window.start.isoformat(),
                "window_end": window.end.isoformat(),
            },
        )
        assert protected.status_code in {401, 403}
    finally:
        anonymous.close()

    logout = client.post(
        "/api/v1/auth/logout",
        headers={CSRF_HEADER_NAME: csrf, "Origin": TEST_ORIGIN},
    )
    assert logout.status_code == 204
