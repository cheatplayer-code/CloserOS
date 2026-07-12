"""Integration tests for human-approved outbound messaging."""

# mypy: ignore-errors

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from closeros.application.authentication_workflows import AuthenticationWorkflowService
from closeros.application.conversation_query_service import ConversationDetail
from closeros.domain.authentication import AuthenticationAssuranceLevel, AuthenticationSessionStage
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.conversation_thread import ConversationThread
from closeros.domain.identity import Role
from closeros.domain.outbound_message import OutboundMessageKind
from closeros.domain.whatsapp_messaging_policy import WhatsAppMessagingPolicy
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
from tests.canonical_persistence_support import synthetic_adapter_metadata
from tests.encryption_support import (
    SERVICE_ID,
    TEST_KEY_VERSION_V1,
    build_test_key_provider,
)
from tests.tenant_persistence_support import TENANT_A_ID, synthetic_membership, synthetic_tenant
from tests.vw_support import (
    CUSTOMER_WA_ID,
    VW_CHANNEL_CONNECTION_ID,
    VW_THREAD_ID,
    recent_customer_inbound_at,
    stale_customer_inbound_at,
    vw_channel_connection,
    vw_whatsapp_connection,
)

pytestmark = pytest.mark.vw_persistence

SESSION_TOKEN = RawAuthenticationToken(deterministic_token_string(TOKEN_ENTROPY_A))


class StubConversationQueryService:
    async def get_conversation_detail(self, **kwargs: object) -> ConversationDetail:
        thread = ConversationThread(
            id=VW_THREAD_ID,
            tenant_id=TENANT_A_ID,
            channel_connection_id=VW_CHANNEL_CONNECTION_ID,
            external_conversation_id=CUSTOMER_WA_ID,
            sales_case_id=None,
            lifecycle_status=None,
            adapter_metadata=synthetic_adapter_metadata(provider="whatsapp_cloud"),
            created_at=NOW,
            updated_at=NOW,
        )
        return ConversationDetail(
            thread=thread,
            manager_user_id=None,
            messages=(),
            analyses=(),
            tasks=(),
        )


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

    def integrated_factory() -> SqlAlchemyIntegratedUnitOfWork:
        return SqlAlchemyIntegratedUnitOfWork(auth_session_factory)

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
            uuid_factory=uuid4,
            mfa_requirement_policy=ConfigurableMfaRequirementPolicy(),
            mfa_verifier=AcceptingMfaVerifier(),
            key_provider=build_test_key_provider(active_version=TEST_KEY_VERSION_V1),
            conversation_query_service=cast(Any, StubConversationQueryService()),
        ),
    )
    client = TestClient(app, base_url="http://testserver")

    async def seed() -> None:
        from closeros.infrastructure import whatsapp_mappers as whatsapp_mappers
        from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

        platform = SqlAlchemyPlatformUnitOfWork(auth_session_factory)
        async with platform:
            await platform.users.add(synthetic_user())
            await platform.tenants.add(synthetic_tenant())
            await platform.memberships.add(synthetic_membership(roles=frozenset({Role.OWNER})))
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
            await integrated.channel_connections.add(vw_channel_connection())
            await integrated.whatsapp_cloud_connections.add(
                record=whatsapp_mappers.domain_to_record(vw_whatsapp_connection()),
            )
            await integrated.conversation_threads.add(
                ConversationThread(
                    id=VW_THREAD_ID,
                    tenant_id=TENANT_A_ID,
                    channel_connection_id=VW_CHANNEL_CONNECTION_ID,
                    external_conversation_id=CUSTOMER_WA_ID,
                    sales_case_id=None,
                    lifecycle_status=None,
                    adapter_metadata=synthetic_adapter_metadata(provider="whatsapp_cloud"),
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await integrated.commit()

    asyncio.run(seed())
    client.cookies.set("closeros_dev_session", SESSION_TOKEN.value)
    return client


def _headers() -> dict[str, str]:
    return {
        "Origin": TEST_ORIGIN,
        CSRF_HEADER_NAME: generate_csrf_token(
            session_token=SESSION_TOKEN,
            secret=TEST_CSRF_SECRET,
        ),
    }


def test_outbound_messages_create_draft_and_approve(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    draft = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/conversations/{VW_THREAD_ID}/outbound-drafts",
        json={"kind": "free_form_text", "body_text": "Follow-up on pricing"},
        headers=_headers(),
    )
    assert draft.status_code == 201
    assert draft.json()["status"] == "draft"
    message_id = draft.json()["id"]
    version = draft.json()["version"]

    approved = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/outbound-messages/{message_id}/approve",
        json={"version": version},
        headers=_headers(),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "queued"
    assert approved.json()["approved_by_user_id"] == str(USER_ID)


def test_outbound_messages_cancel_draft(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    draft = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/conversations/{VW_THREAD_ID}/outbound-drafts",
        json={"kind": "free_form_text", "body_text": "Cancel me"},
        headers=_headers(),
    )
    message_id = draft.json()["id"]
    version = draft.json()["version"]
    cancelled = client.post(
        f"/api/v1/tenants/{TENANT_A_ID}/outbound-messages/{message_id}/cancel",
        json={"version": version},
        headers=_headers(),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_messaging_policy_blocks_free_form_without_customer_window() -> None:
    policy = WhatsAppMessagingPolicy()
    with pytest.raises(Exception, match="template_required"):
        policy.require_allowed(
            kind=OutboundMessageKind.FREE_FORM_TEXT,
            last_customer_inbound_at=stale_customer_inbound_at(),
            now=NOW,
        )


def test_messaging_policy_allows_free_form_with_recent_inbound() -> None:
    policy = WhatsAppMessagingPolicy()
    policy.require_allowed(
        kind=OutboundMessageKind.FREE_FORM_TEXT,
        last_customer_inbound_at=recent_customer_inbound_at(),
        now=NOW,
    )
