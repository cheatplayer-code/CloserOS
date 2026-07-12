"""Integration tests for webhook HTTP routes."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any, cast
from uuid import uuid4

import pytest
from closeros.application.authentication_workflows import AuthenticationWorkflowService
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher
from closeros_api.app import create_app
from closeros_api.auth_ports import (
    AcceptingMfaVerifier,
    CaptureNotificationDispatcher,
    ConfigurableMfaRequirementPolicy,
    InMemoryRateLimiter,
)
from closeros_api.composition import ApiRuntimeOverrides
from fastapi.testclient import TestClient

from tests.auth_api_support import NOW, FixedClock, development_api_settings
from tests.encryption_support import SERVICE_ID, TEST_KEY_VERSION_V1, build_test_key_provider
from tests.ingestion_support import (
    SYNTHETIC_CONNECTION_ID,
    SYNTHETIC_WEBHOOK_SECRET,
    build_synthetic_message_received_payload,
    build_synthetic_webhook_headers,
    synthetic_webhook_connection,
)
from tests.tenant_persistence_support import synthetic_tenant

pytestmark = pytest.mark.jk_persistence


def _build_api_client(auth_test_database_url: str, auth_session_factory: Any) -> TestClient:
    from closeros.infrastructure.audit_unit_of_work import SqlAlchemyAuditUnitOfWork
    from closeros.infrastructure.authentication_unit_of_work import (
        SqlAlchemyAuthenticationUnitOfWork,
    )
    from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
    from closeros.infrastructure.platform_unit_of_work import SqlAlchemyPlatformUnitOfWork
    from closeros.infrastructure.tenant_unit_of_work import SqlAlchemyTenantUnitOfWork

    settings = replace(
        development_api_settings(database_url=auth_test_database_url),
        ingestion_service_id=SERVICE_ID,
    )

    def auth_uow_factory() -> SqlAlchemyAuthenticationUnitOfWork:
        return SqlAlchemyAuthenticationUnitOfWork(auth_session_factory)

    workflow_service = AuthenticationWorkflowService(
        uow_factory=cast(Any, auth_uow_factory),
        password_hasher=Argon2idPasswordHasher(),
        session_touch_interval=settings.session_touch_interval,
    )

    app = create_app(
        settings=settings,
        overrides=ApiRuntimeOverrides(
            workflow_service=workflow_service,
            uow_factory=cast(Any, auth_uow_factory),
            platform_uow_factory=cast(
                Any,
                lambda: SqlAlchemyPlatformUnitOfWork(auth_session_factory),
            ),
            tenant_uow_factory=cast(
                Any,
                lambda: SqlAlchemyTenantUnitOfWork(auth_session_factory),
            ),
            audit_uow_factory=cast(
                Any,
                lambda: SqlAlchemyAuditUnitOfWork(auth_session_factory),
            ),
            integrated_uow_factory=lambda: SqlAlchemyIntegratedUnitOfWork(auth_session_factory),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
            clock=FixedClock(NOW),
            uuid_factory=uuid4,
            mfa_requirement_policy=ConfigurableMfaRequirementPolicy(),
            mfa_verifier=AcceptingMfaVerifier(),
            key_provider=build_test_key_provider(active_version=TEST_KEY_VERSION_V1),
        ),
    )
    return TestClient(app, base_url="http://testserver")


async def _seed_connection(auth_session_factory: Any) -> None:
    from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

    uow = SqlAlchemyIntegratedUnitOfWork(auth_session_factory)
    async with uow:
        await uow.tenants.add(synthetic_tenant())
        await uow.channel_connections.add(synthetic_webhook_connection())
        await uow.commit()


def test_webhooks_api_accepts_valid_request(
    auth_session_factory: Any, auth_test_database_url: str
) -> None:
    async def seed() -> None:
        await _seed_connection(auth_session_factory)

    asyncio.run(seed())
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    body = build_synthetic_message_received_payload()
    headers = build_synthetic_webhook_headers(body=body, secret=SYNTHETIC_WEBHOOK_SECRET)
    response = client.post(
        f"/api/v1/webhooks/synthetic/{SYNTHETIC_CONNECTION_ID}",
        content=body,
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}


def test_webhooks_api_denies_invalid_signature(
    auth_session_factory: Any, auth_test_database_url: str
) -> None:
    async def seed() -> None:
        await _seed_connection(auth_session_factory)

    asyncio.run(seed())
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    body = build_synthetic_message_received_payload()
    headers = build_synthetic_webhook_headers(body=body, secret=SYNTHETIC_WEBHOOK_SECRET)
    headers["x-synthetic-signature"] = "invalid"
    response = client.post(
        f"/api/v1/webhooks/synthetic/{SYNTHETIC_CONNECTION_ID}",
        content=body,
        headers=headers,
    )
    assert response.status_code == 403


def test_webhooks_api_denies_unknown_provider(
    auth_session_factory: Any, auth_test_database_url: str
) -> None:
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    body = build_synthetic_message_received_payload()
    response = client.post(
        f"/api/v1/webhooks/whatsapp/{SYNTHETIC_CONNECTION_ID}",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 403


def test_webhooks_api_denies_oversized_body(
    auth_session_factory: Any, auth_test_database_url: str
) -> None:
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    body = b"x" * (1024 * 1024 + 1)
    response = client.post(
        f"/api/v1/webhooks/synthetic/{SYNTHETIC_CONNECTION_ID}",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 403
