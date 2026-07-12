"""Authentication and audit integration tests."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import psycopg
import pytest
from closeros.application.authentication_workflows import (
    AuthenticationFailedError,
    AuthenticationWorkflowService,
)
from closeros.domain.audit import AuditAction
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher
from closeros_api.app import create_app
from closeros_api.auth_ports import CaptureNotificationDispatcher, InMemoryRateLimiter
from closeros_api.composition import AuthRuntimeOverrides
from closeros_api.request_correlation import REQUEST_CORRELATION_HEADER
from fastapi.testclient import TestClient
from sqlalchemy import make_url

from tests.auth_api_support import (
    CREDENTIAL_ID,
    NOW,
    SESSION_ID,
    TEST_EMAIL,
    TEST_PASSWORD,
    USER_ID,
    VERIFICATION_TOKEN_ID,
    FixedClock,
    SequenceUuidFactory,
    development_api_settings,
)
from tests.auth_workflow_support import TEST_AUDIT_CONTEXT, deterministic_token_factory
from tests.conftest import _rebuild_database_url
from tests.test_audit_support import CORRELATION_ID

pytestmark = pytest.mark.auth_persistence


def _build_client(auth_uow_factory: Any, auth_test_database_url: str) -> TestClient:
    settings = development_api_settings(database_url=auth_test_database_url)
    workflow_service = AuthenticationWorkflowService(
        uow_factory=auth_uow_factory,
        password_hasher=Argon2idPasswordHasher(),
        session_touch_interval=settings.session_touch_interval,
    )
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=workflow_service,
            uow_factory=auth_uow_factory,
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
            clock=FixedClock(NOW),
            uuid_factory=SequenceUuidFactory(
                [
                    USER_ID,
                    CREDENTIAL_ID,
                    VERIFICATION_TOKEN_ID,
                    SESSION_ID,
                ]
            ),
        ),
    )
    return TestClient(app)


def test_registration_commits_matching_audit_event(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    async def exercise() -> None:
        service = AuthenticationWorkflowService(
            uow_factory=auth_uow_factory,
            password_hasher=Argon2idPasswordHasher(),
        )
        await service.register_user(
            user_id=USER_ID,
            credential_id=CREDENTIAL_ID,
            verification_token_id=VERIFICATION_TOKEN_ID,
            email=TEST_EMAIL,
            plaintext_password=TEST_PASSWORD,
            registered_at=NOW,
            audit_context=TEST_AUDIT_CONTEXT,
            raw_token_factory=deterministic_token_factory(bytes(range(32))),
        )

    asyncio.run(exercise())

    direct_url = _rebuild_database_url(
        auth_test_database_url,
        database=make_url(auth_test_database_url).database or "postgres",
        sqlalchemy=False,
    )
    with psycopg.connect(direct_url) as connection:
        row = connection.execute(
            "SELECT action, correlation_id FROM audit_events WHERE action = %s",
            (AuditAction.USER_REGISTRATION_COMPLETED.value,),
        ).fetchone()
    assert row is not None
    assert row[0] == AuditAction.USER_REGISTRATION_COMPLETED.value
    assert UUID(str(row[1])) == TEST_AUDIT_CONTEXT.correlation_id


def test_failed_login_records_sanitized_audit_event(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    async def exercise() -> None:
        service = AuthenticationWorkflowService(
            uow_factory=auth_uow_factory,
            password_hasher=Argon2idPasswordHasher(),
        )
        with pytest.raises(AuthenticationFailedError):
            await service.login_with_password(
                email=TEST_EMAIL,
                plaintext_password=TEST_PASSWORD,
                session_id=SESSION_ID,
                authenticated_at=NOW,
                audit_context=TEST_AUDIT_CONTEXT,
            )

    asyncio.run(exercise())

    direct_url = _rebuild_database_url(
        auth_test_database_url,
        database=make_url(auth_test_database_url).database or "postgres",
        sqlalchemy=False,
    )
    with psycopg.connect(direct_url) as connection:
        row = connection.execute(
            """
            SELECT actor_type, actor_id, metadata
            FROM audit_events
            WHERE action = %s
            """,
            (AuditAction.AUTH_LOGIN_FAILED.value,),
        ).fetchone()
    assert row is not None
    assert row[0] == "anonymous"
    assert row[1] is None
    metadata = row[2]
    assert "password" not in str(metadata)
    assert "email" not in str(metadata)


def test_correlation_id_is_generated_and_returned(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_client(auth_uow_factory, auth_test_database_url)
    response = client.get("/health")
    assert response.status_code == 200
    assert REQUEST_CORRELATION_HEADER in response.headers
    assert response.headers[REQUEST_CORRELATION_HEADER]


def test_client_request_id_header_is_ignored(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    client = _build_client(auth_uow_factory, auth_test_database_url)
    forged = str(CORRELATION_ID)
    response = client.get("/health", headers={REQUEST_CORRELATION_HEADER: forged})
    assert response.headers[REQUEST_CORRELATION_HEADER] != forged
