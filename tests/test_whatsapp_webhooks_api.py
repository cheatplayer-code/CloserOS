"""Integration tests for WhatsApp Cloud webhook HTTP routes."""

# mypy: ignore-errors

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any, cast
from uuid import uuid4

import pytest
from closeros.application.atomic_content_commands import AtomicContentCommandService
from closeros.application.authentication_workflows import AuthenticationWorkflowService
from closeros.application.provider_adapter_registry import ProviderAdapterRegistry
from closeros.application.webhook_ingestion import WebhookIngestionService
from closeros.infrastructure.in_memory_webhook_rate_limiter import InMemoryWebhookRateLimiter
from closeros.infrastructure.injected_whatsapp_credential_resolver import (
    InjectedWhatsAppCredentialResolver,
)
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher
from closeros.infrastructure.synthetic_hmac_adapter import SyntheticHmacWebhookAdapter
from closeros.infrastructure.whatsapp_cloud_adapter import WhatsAppCloudWebhookAdapter
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
from tests.encryption_support import (
    SERVICE_ID,
    TEST_KEY_VERSION_V1,
    build_content_encryption_service,
    build_test_key_provider,
)
from tests.ingestion_support import SYNTHETIC_WEBHOOK_SECRET
from tests.tenant_persistence_support import synthetic_tenant
from tests.vw_support import (
    GRAPH_API_VERSION,
    VW_APP_SECRET,
    VW_APP_SECRET_REF,
    VW_CHANNEL_CONNECTION_ID,
    VW_VERIFY_TOKEN,
    VW_VERIFY_TOKEN_REF,
    VW_WEBHOOK_PUBLIC_KEY,
    build_whatsapp_text_message_payload,
    build_whatsapp_webhook_headers,
    vw_channel_connection,
    vw_whatsapp_connection,
    whatsapp_hub_verify_query,
)
from tests.vw_support import vw_whatsapp_connection as _vw_whatsapp_connection_factory

pytestmark = pytest.mark.vw_persistence


def _build_whatsapp_adapter_registry(
    integrated_uow_factory: Any,
) -> ProviderAdapterRegistry:
    resolver = InjectedWhatsAppCredentialResolver(
        secrets_by_reference={VW_APP_SECRET_REF: VW_APP_SECRET},
    )

    async def resolve_app_secret_for_channel(
        tenant_id: object, channel_connection_id: object
    ) -> object:
        from closeros.domain.provider_credentials import SecretBytes

        _ = channel_connection_id
        secret = await resolver.resolve_app_secret(
            tenant_id=tenant_id,  # type: ignore[arg-type]
            whatsapp_connection_id=_vw_whatsapp_connection_factory().id,
            reference_key=VW_APP_SECRET_REF,
        )
        return secret if isinstance(secret, SecretBytes) else None

    return ProviderAdapterRegistry(
        adapters=(
            SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET),
            WhatsAppCloudWebhookAdapter(
                resolve_app_secret_for_channel=resolve_app_secret_for_channel,
                graph_api_version=GRAPH_API_VERSION,
            ),
        ),
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

    content_encryption = build_content_encryption_service(integrated_factory)
    atomic_commands = AtomicContentCommandService(
        uow_factory=integrated_factory,
        content_encryption=content_encryption,
    )
    webhook_ingestion = WebhookIngestionService(
        uow_factory=integrated_factory,
        atomic_commands=atomic_commands,
        adapter_registry=_build_whatsapp_adapter_registry(integrated_factory),
        rate_limiter=InMemoryWebhookRateLimiter(),
        service_actor_id=SERVICE_ID,
        uuid_factory=uuid4,
        webhook_rate_limit=120,
        webhook_rate_window_seconds=60,
    )

    def auth_uow_factory() -> SqlAlchemyAuthenticationUnitOfWork:
        return SqlAlchemyAuthenticationUnitOfWork(auth_session_factory)

    workflow_service = AuthenticationWorkflowService(
        uow_factory=cast(Any, auth_uow_factory),
        password_hasher=Argon2idPasswordHasher(),
        session_touch_interval=settings.session_touch_interval,
    )

    from closeros.application.whatsapp_webhook_verification_service import (
        WhatsAppWebhookVerificationService,
    )
    from closeros.infrastructure.injected_whatsapp_credential_resolver import (
        InjectedWhatsAppCredentialResolver,
    )

    credential_resolver = InjectedWhatsAppCredentialResolver(
        secrets_by_reference={
            VW_APP_SECRET_REF: VW_APP_SECRET,
            VW_VERIFY_TOKEN_REF: VW_VERIFY_TOKEN,
        },
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
            webhook_ingestion=webhook_ingestion,
            whatsapp_credential_resolver=credential_resolver,
            whatsapp_webhook_verification_service=WhatsAppWebhookVerificationService(
                uow_factory=integrated_factory,
                credential_resolver=credential_resolver,
            ),
        ),
    )
    return TestClient(app, base_url="http://testserver")


async def _seed_whatsapp_connection(auth_session_factory: Any) -> None:
    from closeros.infrastructure import whatsapp_mappers as whatsapp_mappers
    from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

    uow = SqlAlchemyIntegratedUnitOfWork(auth_session_factory)
    async with uow:
        await uow.tenants.add(synthetic_tenant())
        await uow.channel_connections.add(vw_channel_connection())
        await uow.whatsapp_cloud_connections.add(
            record=whatsapp_mappers.domain_to_record(vw_whatsapp_connection()),
        )
        await uow.commit()


def test_whatsapp_webhook_get_verification_returns_challenge(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    async def seed() -> None:
        await _seed_whatsapp_connection(auth_session_factory)

    asyncio.run(seed())
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    response = client.get(
        f"/api/v1/webhooks/whatsapp_cloud/{VW_WEBHOOK_PUBLIC_KEY}",
        params=whatsapp_hub_verify_query(),
    )
    assert response.status_code == 200
    assert response.text == "challenge-token-12345"


def test_whatsapp_webhook_get_verification_denies_invalid_token(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    async def seed() -> None:
        await _seed_whatsapp_connection(auth_session_factory)

    asyncio.run(seed())
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    params = whatsapp_hub_verify_query()
    params["hub.verify_token"] = "wrong-token"
    response = client.get(
        f"/api/v1/webhooks/whatsapp_cloud/{VW_WEBHOOK_PUBLIC_KEY}",
        params=params,
    )
    assert response.status_code == 403


def test_whatsapp_webhook_post_accepts_valid_signature(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    async def seed() -> None:
        await _seed_whatsapp_connection(auth_session_factory)

    asyncio.run(seed())
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    body = build_whatsapp_text_message_payload()
    headers = build_whatsapp_webhook_headers(body=body)
    response = client.post(
        f"/api/v1/webhooks/whatsapp_cloud/{VW_CHANNEL_CONNECTION_ID}",
        content=body,
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}


def test_whatsapp_webhook_post_denies_invalid_signature(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    async def seed() -> None:
        await _seed_whatsapp_connection(auth_session_factory)

    asyncio.run(seed())
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    body = build_whatsapp_text_message_payload()
    headers = build_whatsapp_webhook_headers(body=body)
    headers["x-hub-signature-256"] = "sha256=invalid"
    response = client.post(
        f"/api/v1/webhooks/whatsapp_cloud/{VW_CHANNEL_CONNECTION_ID}",
        content=body,
        headers=headers,
    )
    assert response.status_code == 403


def test_whatsapp_webhook_post_is_idempotent(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    async def seed() -> None:
        await _seed_whatsapp_connection(auth_session_factory)

    asyncio.run(seed())
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    body = build_whatsapp_text_message_payload()
    headers = build_whatsapp_webhook_headers(body=body)
    path = f"/api/v1/webhooks/whatsapp_cloud/{VW_CHANNEL_CONNECTION_ID}"
    first = client.post(path, content=body, headers=headers)
    second = client.post(path, content=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200

    async def count_events() -> int:
        from closeros.infrastructure.canonical_orm import WebhookEventRow
        from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
        from sqlalchemy import func, select

        uow = SqlAlchemyIntegratedUnitOfWork(auth_session_factory)
        async with uow:
            result = await uow.session.execute(
                select(func.count())
                .select_from(WebhookEventRow)
                .where(WebhookEventRow.channel_connection_id == VW_CHANNEL_CONNECTION_ID)
            )
            return int(result.scalar_one())

    assert asyncio.run(count_events()) == 1


def test_whatsapp_webhook_post_denies_unknown_connection(
    auth_session_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_api_client(auth_test_database_url, auth_session_factory)
    body = build_whatsapp_text_message_payload()
    headers = build_whatsapp_webhook_headers(body=body)
    response = client.post(
        f"/api/v1/webhooks/whatsapp_cloud/{VW_CHANNEL_CONNECTION_ID}",
        content=body,
        headers=headers,
    )
    assert response.status_code == 403
