"""Integration tests for WhatsApp Cloud integration administration HTTP routes."""

# mypy: ignore-errors

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, cast

import pytest
from closeros.application.authentication_workflows import AuthenticationWorkflowService
from closeros.domain.authentication import AuthenticationAssuranceLevel, AuthenticationSessionStage
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.identity import Role
from closeros.infrastructure.injected_whatsapp_credential_resolver import (
    InjectedWhatsAppCredentialResolver,
)
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
from tests.encryption_support import TEST_KEY_VERSION_V1, build_test_key_provider
from tests.tenant_persistence_support import TENANT_A_ID, synthetic_membership, synthetic_tenant
from tests.vw_support import (
    GRAPH_API_VERSION,
    PHONE_NUMBER_ID,
    VW_ACCESS_TOKEN,
    VW_ACCESS_TOKEN_REF,
    VW_APP_SECRET,
    VW_APP_SECRET_REF,
    VW_VERIFY_TOKEN,
    VW_VERIFY_TOKEN_REF,
    vw_channel_connection,
    vw_whatsapp_connection,
)

pytestmark = pytest.mark.vw_persistence

SESSION_TOKEN = RawAuthenticationToken(deterministic_token_string(TOKEN_ENTROPY_A))


def _build_api_client(
    auth_test_database_url: str,
    auth_session_factory: Any,
    *,
    roles: frozenset[Role],
) -> TestClient:
    from closeros.infrastructure.audit_unit_of_work import SqlAlchemyAuditUnitOfWork
    from closeros.infrastructure.authentication_unit_of_work import (
        SqlAlchemyAuthenticationUnitOfWork,
    )
    from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
    from closeros.infrastructure.platform_unit_of_work import SqlAlchemyPlatformUnitOfWork
    from closeros.infrastructure.tenant_unit_of_work import SqlAlchemyTenantUnitOfWork

    settings = development_api_settings(database_url=auth_test_database_url)

    def integrated_factory() -> SqlAlchemyIntegratedUnitOfWork:
        return SqlAlchemyIntegratedUnitOfWork(auth_session_factory)

    credential_resolver = InjectedWhatsAppCredentialResolver(
        secrets_by_reference={
            VW_ACCESS_TOKEN_REF: VW_ACCESS_TOKEN,
            VW_APP_SECRET_REF: VW_APP_SECRET,
            VW_VERIFY_TOKEN_REF: VW_VERIFY_TOKEN,
        },
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
            integrated_uow_factory=integrated_factory,
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
            clock=FixedClock(NOW),
            mfa_requirement_policy=ConfigurableMfaRequirementPolicy(),
            mfa_verifier=AcceptingMfaVerifier(),
            key_provider=build_test_key_provider(active_version=TEST_KEY_VERSION_V1),
            whatsapp_credential_resolver=credential_resolver,
        ),
    )
    client = TestClient(app, base_url="http://testserver")

    async def seed() -> None:
        platform = SqlAlchemyPlatformUnitOfWork(auth_session_factory)
        async with platform:
            await platform.users.add(synthetic_user())
            await platform.tenants.add(synthetic_tenant())
            await platform.memberships.add(synthetic_membership(roles=roles))
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


def _create_payload() -> dict[str, str | None]:
    return {
        "app_id": "900100200300",
        "waba_id": "800100200300",
        "phone_number_id": PHONE_NUMBER_ID,
        "display_phone_number": "+15550001",
        "graph_api_version": GRAPH_API_VERSION,
        "access_token_ref": VW_ACCESS_TOKEN_REF,
        "app_secret_ref": VW_APP_SECRET_REF,
        "verify_token_ref": VW_VERIFY_TOKEN_REF,
    }


def test_whatsapp_integrations_api_create_and_list(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_api_client(
        auth_test_database_url,
        auth_session_factory,
        roles=frozenset({Role.OWNER}),
    )
    create = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/integrations/whatsapp",
        json=_create_payload(),
        headers=_authenticated_headers(),
    )
    assert create.status_code == 201
    body = create.json()
    assert body["provider"] == "whatsapp_cloud"
    assert body["access_token_ref"] == VW_ACCESS_TOKEN_REF
    assert VW_ACCESS_TOKEN.decode("utf-8") not in create.text
    assert VW_APP_SECRET.decode("utf-8") not in create.text

    listing = client.get(f"/api/v1/tenants/{TENANT_A_ID}/integrations/whatsapp")
    assert listing.status_code == 200
    assert len(listing.json()["connections"]) == 1


def test_whatsapp_integrations_api_manager_cannot_create(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_api_client(
        auth_test_database_url,
        auth_session_factory,
        roles=frozenset({Role.MANAGER}),
    )
    response = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/integrations/whatsapp",
        json=_create_payload(),
        headers=_authenticated_headers(),
    )
    assert response.status_code == 403


def test_whatsapp_integrations_api_update_connection(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_api_client(
        auth_test_database_url,
        auth_session_factory,
        roles=frozenset({Role.COMPLIANCE_ADMIN}),
    )
    created = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/integrations/whatsapp",
        json=_create_payload(),
        headers=_authenticated_headers(),
    )
    connection_id = created.json()["id"]
    version = created.json()["version"]
    updated = client.patch(
        f"/api/v1/tenants/{TENANT_A_ID}/integrations/whatsapp/{connection_id}",
        json={
            **_create_payload(),
            "display_phone_number": "+15550002",
            "version": version,
        },
        headers=_authenticated_headers(),
    )
    assert updated.status_code == 200
    assert updated.json()["display_phone_number"] == "+15550002"
    assert VW_APP_SECRET.decode("utf-8") not in updated.text


def test_whatsapp_integrations_api_sales_head_can_read(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    async def seed_connection() -> None:
        from closeros.infrastructure import whatsapp_mappers as whatsapp_mappers
        from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

        integrated = SqlAlchemyIntegratedUnitOfWork(auth_session_factory)
        async with integrated:
            await integrated.channel_connections.add(vw_channel_connection())
            await integrated.whatsapp_cloud_connections.add(
                record=whatsapp_mappers.domain_to_record(vw_whatsapp_connection()),
            )
            await integrated.commit()

    asyncio.run(seed_connection())

    client = _build_api_client(
        auth_test_database_url,
        auth_session_factory,
        roles=frozenset({Role.SALES_HEAD}),
    )
    response = client.get(f"/api/v1/tenants/{TENANT_A_ID}/integrations/whatsapp")
    assert response.status_code == 200
