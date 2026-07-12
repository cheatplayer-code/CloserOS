"""Integration tests for CSV import HTTP routes."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast

import pytest
from closeros.application.authentication_workflows import AuthenticationWorkflowService
from closeros.domain.authentication import AuthenticationAssuranceLevel, AuthenticationSessionStage
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.identity import Role
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher
from closeros.security.authentication_tokens import (
    RawAuthenticationToken,
    hash_authentication_token,
)
from closeros_api.app import create_app
from closeros_api.auth_ports import (
    AcceptingMfaVerifier,
    CaptureNotificationDispatcher,
    ConfigurableMfaRequirementPolicy,
    InMemoryRateLimiter,
)
from closeros_api.auth_security import CSRF_HEADER_NAME, generate_csrf_token
from closeros_api.composition import ApiRuntimeOverrides
from fastapi.testclient import TestClient

from tests.auth_api_support import (
    NOW,
    TEST_CSRF_SECRET,
    TEST_ORIGIN,
    TOKEN_ENTROPY_A,
    FixedClock,
    deterministic_token_string,
    development_api_settings,
)
from tests.auth_persistence_support import SESSION_ID, USER_ID, synthetic_user
from tests.encryption_support import SERVICE_ID, TEST_KEY_VERSION_V1, build_test_key_provider
from tests.ingestion_support import (
    default_csv_mapping,
    sample_csv_bytes,
    synthetic_webhook_connection,
)
from tests.tenant_persistence_support import TENANT_A_ID, synthetic_membership, synthetic_tenant

pytestmark = pytest.mark.jk_persistence

SESSION_TOKEN = RawAuthenticationToken(deterministic_token_string(TOKEN_ENTROPY_A))


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
            mfa_requirement_policy=ConfigurableMfaRequirementPolicy(),
            mfa_verifier=AcceptingMfaVerifier(),
            key_provider=build_test_key_provider(active_version=TEST_KEY_VERSION_V1),
        ),
    )
    client = TestClient(app, base_url="http://testserver")

    async def seed() -> None:
        from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
        from closeros.infrastructure.platform_unit_of_work import SqlAlchemyPlatformUnitOfWork

        platform = SqlAlchemyPlatformUnitOfWork(auth_session_factory)
        async with platform:
            await platform.users.add(synthetic_user())
            await platform.tenants.add(synthetic_tenant())
            await platform.memberships.add(
                synthetic_membership(roles=frozenset({Role.OWNER})),
            )
            await platform.sessions.add(
                AuthenticationSession(
                    id=SESSION_ID,
                    user_id=USER_ID,
                    token_hash=hash_authentication_token(SESSION_TOKEN),
                    stage=AuthenticationSessionStage.AUTHENTICATED,
                    assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
                    mfa_completed=True,
                    created_at=NOW,
                    last_seen_at=NOW,
                    expires_at=NOW + timedelta(hours=12),
                    revoked_at=None,
                )
            )
            await platform.commit()

        integrated = SqlAlchemyIntegratedUnitOfWork(auth_session_factory)
        async with integrated:
            await integrated.channel_connections.add(synthetic_webhook_connection())
            await integrated.commit()

    asyncio.run(seed())
    client.cookies.set("closeros_dev_session", SESSION_TOKEN.value)
    return client


def _authenticated_headers() -> dict[str, str]:
    return {
        "Origin": TEST_ORIGIN,
        CSRF_HEADER_NAME: generate_csrf_token(
            session_token=SESSION_TOKEN,
            secret=TEST_CSRF_SECRET,
        ),
    }


def test_csv_import_api_preview_requires_lawful_source_header(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    response = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/csv-imports/preview"
        f"?channel_connection_id={synthetic_webhook_connection().id}",
        content=sample_csv_bytes(),
        headers={**_authenticated_headers(), "Content-Type": "text/csv"},
    )
    assert response.status_code == 400


def test_csv_import_api_preview_success(
    auth_session_factory: Any, auth_test_database_url: str
) -> None:
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    response = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/csv-imports/preview"
        f"?channel_connection_id={synthetic_webhook_connection().id}",
        content=sample_csv_bytes(),
        headers={
            **_authenticated_headers(),
            "Content-Type": "text/csv",
            "X-Lawful-Source-Confirmed": "true",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 1
    assert "import_id" in body


def test_csv_import_api_start_and_status(
    auth_session_factory: Any, auth_test_database_url: str
) -> None:
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    preview = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/csv-imports/preview"
        f"?channel_connection_id={synthetic_webhook_connection().id}",
        content=sample_csv_bytes(),
        headers={
            **_authenticated_headers(),
            "Content-Type": "text/csv",
            "X-Lawful-Source-Confirmed": "true",
        },
    )
    import_id = preview.json()["import_id"]
    started = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/csv-imports/{import_id}/start",
        json={"mapping": default_csv_mapping()},
        headers=_authenticated_headers(),
    )
    assert started.status_code == 200
    status = client.get(
        f"/api/v1/tenants/{TENANT_A_ID}/csv-imports/{import_id}",
        headers=_authenticated_headers(),
    )
    assert status.status_code == 200
    assert status.json()["status"] in {"uploaded", "ready"}


def test_csv_import_api_denies_without_csrf(
    auth_session_factory: Any, auth_test_database_url: str
) -> None:
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    response = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/csv-imports/preview"
        f"?channel_connection_id={synthetic_webhook_connection().id}",
        content=sample_csv_bytes(),
        headers={
            "Content-Type": "text/csv",
            "Origin": TEST_ORIGIN,
            "X-Lawful-Source-Confirmed": "true",
        },
    )
    assert response.status_code == 403
