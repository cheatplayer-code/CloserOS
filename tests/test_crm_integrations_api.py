"""Integration tests for CRM integration administration HTTP routes."""

# mypy: ignore-errors

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.application.authentication_workflows import AuthenticationWorkflowService
from closeros.application.crm_connection_service import CrmConnectionService
from closeros.application.crm_ports import (
    CrmAdapter,
    CrmChangedSyncPage,
    CrmContactSnapshot,
    CrmContactSyncPage,
    CrmContactWrite,
    CrmDealSnapshot,
    CrmDealWrite,
    CrmOutcomeApply,
    CrmSyncPage,
)
from closeros.application.crm_reconciliation_service import CrmReconciliationService
from closeros.application.crm_sync_service import CrmSyncService
from closeros.domain.authentication import AuthenticationAssuranceLevel, AuthenticationSessionStage
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.crm_connection import CrmConnection, CrmConnectionStatus
from closeros.domain.crm_provider import CrmProviderCode
from closeros.domain.identity import Role
from closeros.infrastructure.injected_crm_credential_resolver import InjectedCrmCredentialResolver
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
    SequenceUuidFactory,
    deterministic_token_string,
    development_api_settings,
)
from tests.auth_persistence_support import SESSION_ID, USER_ID, synthetic_user
from tests.encryption_support import TEST_KEY_VERSION_V1, build_test_key_provider
from tests.tenant_persistence_support import TENANT_A_ID, synthetic_membership, synthetic_tenant
from tests.xy_crm_support import (
    CRM_ACCESS_TOKEN,
    CRM_ACCESS_TOKEN_REF,
    CRM_CONNECTION_ID,
)
from tests.xy_crm_support import (
    NOW as CRM_NOW,
)

pytestmark = pytest.mark.crm_persistence

SESSION_TOKEN = RawAuthenticationToken(deterministic_token_string(TOKEN_ENTROPY_A))


@dataclass(frozen=True, slots=True)
class _MockCrmAdapter(CrmAdapter):
    async def verify_connection(self, *, connection: CrmConnection, access_token: str) -> bool:
        _ = connection, access_token
        return True

    async def get_contact(
        self, *, connection: CrmConnection, access_token: str, external_contact_id: str
    ) -> CrmContactSnapshot:
        _ = connection, access_token
        return CrmContactSnapshot(
            external_contact_id=external_contact_id,
            first_name="Ada",
            last_name="Lovelace",
            email=None,
            phone=None,
            owner_external_id=None,
            updated_at=CRM_NOW,
        )

    async def add_contact(
        self, *, connection: CrmConnection, access_token: str, fields: CrmContactWrite
    ) -> str:
        _ = connection, access_token, fields
        return "9001"

    async def update_contact(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_contact_id: str,
        fields: CrmContactWrite,
    ) -> None:
        _ = connection, access_token, external_contact_id, fields

    async def list_contacts(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        cursor: str | None,
        updated_since: object,
    ) -> CrmContactSyncPage:
        _ = connection, access_token, cursor, updated_since
        return CrmContactSyncPage(contacts=(), next_cursor=None)

    async def get_deal(
        self, *, connection: CrmConnection, access_token: str, external_deal_id: str
    ) -> CrmDealSnapshot:
        _ = connection, access_token
        return CrmDealSnapshot(
            external_deal_id=external_deal_id,
            title="Pilot",
            owner_external_id="7",
            stage="NEW",
            amount_minor=10000,
            currency="KZT",
            outcome="N",
            reason=None,
            contact_external_id=None,
            updated_at=CRM_NOW,
        )

    async def add_deal(
        self, *, connection: CrmConnection, access_token: str, fields: CrmDealWrite
    ) -> str:
        _ = connection, access_token, fields
        return "42"

    async def update_deal(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_deal_id: str,
        fields: CrmDealWrite,
    ) -> None:
        _ = connection, access_token, external_deal_id, fields

    async def list_deals(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        cursor: str | None,
        updated_since: object,
    ) -> CrmSyncPage:
        _ = connection, access_token, cursor, updated_since
        return CrmSyncPage(
            deals=(
                CrmDealSnapshot(
                    external_deal_id="42",
                    title="Pilot",
                    owner_external_id="7",
                    stage="NEW",
                    amount_minor=10000,
                    currency="KZT",
                    outcome="N",
                    reason=None,
                    contact_external_id=None,
                    updated_at=CRM_NOW,
                ),
            ),
            next_cursor=None,
        )

    async def list_changed(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        cursor: str | None,
        updated_since: object,
    ) -> CrmChangedSyncPage:
        page = await self.list_deals(
            connection=connection,
            access_token=access_token,
            cursor=cursor,
            updated_since=updated_since,
        )
        contacts = await self.list_contacts(
            connection=connection,
            access_token=access_token,
            cursor=None,
            updated_since=updated_since,
        )
        return CrmChangedSyncPage(
            contacts=contacts.contacts,
            deals=page.deals,
            next_cursor=page.next_cursor,
        )

    async def apply_outcome(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_deal_id: str,
        outcome: CrmOutcomeApply,
    ) -> None:
        _ = connection, access_token, external_deal_id, outcome


def _build_api_client(
    auth_test_database_url: str,
    auth_session_factory: Any,
    *,
    roles: frozenset[Role],
    seed: bool = True,
) -> TestClient:
    from closeros.infrastructure.audit_unit_of_work import SqlAlchemyAuditUnitOfWork
    from closeros.infrastructure.authentication_unit_of_work import (
        SqlAlchemyAuthenticationUnitOfWork,
    )
    from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
    from closeros.infrastructure.platform_unit_of_work import SqlAlchemyPlatformUnitOfWork
    from closeros.infrastructure.tenant_unit_of_work import SqlAlchemyTenantUnitOfWork

    settings = development_api_settings(database_url=auth_test_database_url)
    clock = FixedClock(NOW)
    uuid_factory = SequenceUuidFactory(
        [
            CRM_CONNECTION_ID,
            UUID("00000000-0000-0000-0000-000000000301"),
            UUID("00000000-0000-0000-0000-000000000302"),
            UUID("00000000-0000-0000-0000-000000000303"),
            UUID("00000000-0000-0000-0000-000000000304"),
            UUID("00000000-0000-0000-0000-000000000305"),
            UUID("00000000-0000-0000-0000-000000000306"),
            UUID("00000000-0000-0000-0000-000000000307"),
            UUID("00000000-0000-0000-0000-000000000308"),
            UUID("00000000-0000-0000-0000-000000000309"),
            UUID("00000000-0000-0000-0000-000000000310"),
        ]
    )

    def integrated_factory() -> SqlAlchemyIntegratedUnitOfWork:
        return SqlAlchemyIntegratedUnitOfWork(auth_session_factory)

    credential_resolver = InjectedCrmCredentialResolver(
        secrets_by_reference={CRM_ACCESS_TOKEN_REF: CRM_ACCESS_TOKEN},
    )
    adapters = {CrmProviderCode.BITRIX24: _MockCrmAdapter()}
    crm_connection_service = CrmConnectionService(
        uow_factory=integrated_factory,
        credential_resolver=credential_resolver,
        adapters=adapters,
        uuid_factory=uuid_factory,
        clock=clock.now,
    )
    crm_sync_service = CrmSyncService(
        uow_factory=integrated_factory,
        credential_resolver=credential_resolver,
        adapters=adapters,
        uuid_factory=uuid_factory,
        clock=clock.now,
    )
    crm_reconciliation_service = CrmReconciliationService(
        uow_factory=integrated_factory,
        sync_service=crm_sync_service,
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
            clock=clock,
            uuid_factory=uuid_factory,
            mfa_requirement_policy=ConfigurableMfaRequirementPolicy(),
            mfa_verifier=AcceptingMfaVerifier(),
            key_provider=build_test_key_provider(active_version=TEST_KEY_VERSION_V1),
            crm_credential_resolver=credential_resolver,
            crm_connection_service=crm_connection_service,
            crm_sync_service=crm_sync_service,
            crm_reconciliation_service=crm_reconciliation_service,
        ),
    )
    client = TestClient(app, base_url="http://testserver")

    async def seed_platform() -> None:
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

    if seed:
        asyncio.run(seed_platform())
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


def _create_payload() -> dict[str, str]:
    return {
        "provider": "bitrix24",
        "portal_domain": "example.bitrix24.kz",
        "access_token_ref": CRM_ACCESS_TOKEN_REF,
    }


def test_crm_integrations_api_create_list_and_sync(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_api_client(
        auth_test_database_url,
        auth_session_factory,
        roles=frozenset({Role.OWNER}),
    )
    create = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/integrations/crm",
        json=_create_payload(),
        headers=_authenticated_headers(),
    )
    assert create.status_code == 201
    body = create.json()
    assert body["provider"] == "bitrix24"
    assert body["access_token_ref"] == CRM_ACCESS_TOKEN_REF
    assert CRM_ACCESS_TOKEN.decode("utf-8") not in create.text

    listing = client.get(f"/api/v1/tenants/{TENANT_A_ID}/integrations/crm")
    assert listing.status_code == 200
    assert len(listing.json()["connections"]) == 1

    connection_id = body["id"]
    version = body["version"]
    verified = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/integrations/crm/{connection_id}/verify",
        json={"version": version},
        headers=_authenticated_headers(),
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "active"

    sync = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/integrations/crm/{connection_id}/sync-once",
        json={"version": verified.json()["version"]},
        headers=_authenticated_headers(),
    )
    assert sync.status_code == 200
    assert sync.json()["status"] == "synced"

    status = client.get(
        f"/api/v1/tenants/{TENANT_A_ID}/integrations/crm/{connection_id}/sync-status"
    )
    assert status.status_code == 200
    assert len(status.json()["attempts"]) >= 1


def test_crm_integrations_api_requires_authentication(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_api_client(
        auth_test_database_url,
        auth_session_factory,
        roles=frozenset({Role.OWNER}),
    )
    client.cookies.clear()
    response = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/integrations/crm",
        json=_create_payload(),
    )
    assert response.status_code == 401


def test_crm_integrations_api_requires_csrf(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_api_client(
        auth_test_database_url,
        auth_session_factory,
        roles=frozenset({Role.OWNER}),
    )
    response = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/integrations/crm",
        json=_create_payload(),
        headers={"Origin": TEST_ORIGIN},
    )
    assert response.status_code == 403


def test_crm_integrations_api_manager_cannot_create(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_api_client(
        auth_test_database_url,
        auth_session_factory,
        roles=frozenset({Role.MANAGER}),
    )
    response = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/integrations/crm",
        json=_create_payload(),
        headers=_authenticated_headers(),
    )
    assert response.status_code == 403


def test_crm_integrations_api_sales_head_can_read(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    from closeros.infrastructure import crm_mappers
    from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

    client = _build_api_client(
        auth_test_database_url,
        auth_session_factory,
        roles=frozenset({Role.SALES_HEAD}),
    )

    async def seed_connection() -> None:
        integrated = SqlAlchemyIntegratedUnitOfWork(auth_session_factory)
        now = NOW
        connection = CrmConnection(
            id=CRM_CONNECTION_ID,
            tenant_id=TENANT_A_ID,
            provider=CrmProviderCode.BITRIX24,
            portal_domain="example.bitrix24.kz",
            client_id_ref=None,
            client_secret_ref=None,
            access_token_ref=CRM_ACCESS_TOKEN_REF,
            refresh_token_ref=None,
            status=CrmConnectionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            last_verified_at=now,
            last_successful_sync_at=None,
            version=1,
        )
        async with integrated:
            await integrated.crm_connections.add(
                record=crm_mappers.connection_domain_to_record(connection)
            )
            await integrated.commit()

    asyncio.run(seed_connection())
    response = client.get(f"/api/v1/tenants/{TENANT_A_ID}/integrations/crm")
    assert response.status_code == 200
    assert len(response.json()["connections"]) == 1


def test_crm_integrations_api_rejects_other_tenant(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_api_client(
        auth_test_database_url,
        auth_session_factory,
        roles=frozenset({Role.OWNER}),
    )
    other_tenant = UUID("99999999-9999-4999-8999-999999999999")
    response = client.get(f"/api/v1/tenants/{other_tenant}/integrations/crm")
    assert response.status_code == 403
