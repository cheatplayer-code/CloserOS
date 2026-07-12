"""PostgreSQL integration tests for the authentication API."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from closeros.application.authentication_workflows import AuthenticationWorkflowService
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher
from closeros_api.app import create_app
from closeros_api.auth_ports import (
    AcceptingMfaVerifier,
    CallableMfaVerifier,
    CaptureNotificationDispatcher,
    ConfigurableMfaRequirementPolicy,
    InMemoryRateLimiter,
)
from closeros_api.auth_security import CSRF_HEADER_NAME
from closeros_api.composition import AuthRuntimeOverrides
from fastapi.testclient import TestClient

from tests.auth_api_support import (
    CREDENTIAL_ID,
    NEW_SESSION_ID,
    NOW,
    OTHER_PASSWORD,
    SESSION_ID,
    TEST_EMAIL,
    TEST_ORIGIN,
    TEST_PASSWORD,
    USER_ID,
    VERIFICATION_TOKEN_ID,
    FixedClock,
    SequenceUuidFactory,
    development_api_settings,
)

pytestmark = pytest.mark.auth_persistence


def _build_api_client(
    auth_uow_factory: Any,
    auth_test_database_url: str,
    *,
    mfa_required: bool = False,
    mfa_verifier: Any = None,
) -> tuple[TestClient, CaptureNotificationDispatcher]:
    settings = development_api_settings(database_url=auth_test_database_url)
    dispatcher = CaptureNotificationDispatcher()
    clock = FixedClock(NOW)
    uuid_factory = SequenceUuidFactory(
        [
            USER_ID,
            CREDENTIAL_ID,
            VERIFICATION_TOKEN_ID,
            SESSION_ID,
            NEW_SESSION_ID,
            UUID("00000000-0000-0000-0000-000000000200"),
            UUID("00000000-0000-0000-0000-000000000201"),
            *[uuid4() for _ in range(20)],
        ]
    )
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
            notification_dispatcher=dispatcher,
            rate_limiter=InMemoryRateLimiter(),
            clock=clock,
            uuid_factory=uuid_factory,
            mfa_requirement_policy=ConfigurableMfaRequirementPolicy(requires_mfa=mfa_required),
            mfa_verifier=mfa_verifier or AcceptingMfaVerifier(),
        ),
    )
    client = TestClient(app, base_url="http://testserver")
    return client, dispatcher


def test_register_verify_login_session_logout_flow(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    client, dispatcher = _build_api_client(auth_uow_factory, auth_test_database_url)

    register = client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert register.status_code == 202
    assert register.headers["Cache-Control"] == "no-store"
    assert len(dispatcher.verification_deliveries) == 1

    raw_verification = dispatcher.verification_deliveries[0].raw_token
    confirm = client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"verification_token": raw_verification.value},
    )
    assert confirm.status_code == 204

    login = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["state"] == "authenticated"
    assert "csrf_token" in body
    assert raw_verification.value not in login.text

    session = client.get("/api/v1/auth/session")
    assert session.status_code == 200
    assert session.json()["user_id"] == str(USER_ID)

    csrf = body["csrf_token"]
    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": TEST_ORIGIN, CSRF_HEADER_NAME: csrf},
    )
    assert logout.status_code == 204

    expired = client.get("/api/v1/auth/session")
    assert expired.status_code == 401


def test_login_failure_is_generic(auth_uow_factory: Any, auth_test_database_url: str) -> None:
    client, dispatcher = _build_api_client(auth_uow_factory, auth_test_database_url)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "authentication failed"
    assert TEST_EMAIL not in response.text


def test_pending_mfa_flow(auth_uow_factory: Any, auth_test_database_url: str) -> None:
    client, dispatcher = _build_api_client(
        auth_uow_factory,
        auth_test_database_url,
        mfa_required=True,
        mfa_verifier=CallableMfaVerifier(lambda _u, _m, _r: True),
    )

    client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    raw_verification = dispatcher.verification_deliveries[0].raw_token
    client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"verification_token": raw_verification.value},
    )

    login = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["state"] == "mfa_required"
    csrf = login.json()["csrf_token"]

    complete = client.post(
        "/api/v1/auth/mfa/complete",
        json={"method": "totp", "response": {"code": "123456"}},
        headers={"Origin": TEST_ORIGIN, CSRF_HEADER_NAME: csrf},
    )
    assert complete.status_code == 200
    assert complete.json()["state"] == "authenticated"

    session = client.get("/api/v1/auth/session")
    assert session.status_code == 200
    assert session.json()["assurance_level"] == "multi_factor"


def test_mfa_complete_rejects_missing_csrf(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    client, dispatcher = _build_api_client(
        auth_uow_factory, auth_test_database_url, mfa_required=True
    )
    client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    raw_verification = dispatcher.verification_deliveries[0].raw_token
    client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"verification_token": raw_verification.value},
    )
    client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )

    response = client.post(
        "/api/v1/auth/mfa/complete",
        json={"method": "totp", "response": {"code": "123456"}},
        headers={"Origin": TEST_ORIGIN},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "access denied"


def test_password_reset_revokes_sessions(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    client, dispatcher = _build_api_client(auth_uow_factory, auth_test_database_url)
    client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    raw_verification = dispatcher.verification_deliveries[0].raw_token
    client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"verification_token": raw_verification.value},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert login.status_code == 200

    reset_request = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": TEST_EMAIL},
    )
    assert reset_request.status_code == 202
    raw_reset = dispatcher.reset_deliveries[0].raw_token

    confirm = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"reset_token": raw_reset.value, "new_password": OTHER_PASSWORD},
    )
    assert confirm.status_code == 204

    assert client.get("/api/v1/auth/session").status_code == 401

    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": OTHER_PASSWORD},
    )
    assert new_login.status_code == 200


def test_password_change_rotates_session(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    client, dispatcher = _build_api_client(auth_uow_factory, auth_test_database_url)
    client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    raw_verification = dispatcher.verification_deliveries[0].raw_token
    client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"verification_token": raw_verification.value},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    csrf = login.json()["csrf_token"]

    changed = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": TEST_PASSWORD, "new_password": OTHER_PASSWORD},
        headers={"Origin": TEST_ORIGIN, CSRF_HEADER_NAME: csrf},
    )
    assert changed.status_code == 200
    assert changed.json()["csrf_token"] != csrf

    assert client.get("/api/v1/auth/session").status_code == 200


def test_verification_request_unknown_email_is_generic(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    client, dispatcher = _build_api_client(auth_uow_factory, auth_test_database_url)
    response = client.post(
        "/api/v1/auth/email-verification/request",
        json={"email": "missing@example.test"},
    )
    assert response.status_code == 202
    assert response.json()["message"] == "request accepted"


def test_dispatcher_failure_does_not_change_accepted_response(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    client, dispatcher = _build_api_client(auth_uow_factory, auth_test_database_url)
    dispatcher.fail_next = RuntimeError("delivery failed")
    response = client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 202


def test_logout_all_requires_authenticated_session(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    client, dispatcher = _build_api_client(auth_uow_factory, auth_test_database_url)
    client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    raw_verification = dispatcher.verification_deliveries[0].raw_token
    client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"verification_token": raw_verification.value},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    csrf = login.json()["csrf_token"]

    response = client.post(
        "/api/v1/auth/logout-all",
        headers={"Origin": TEST_ORIGIN, CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401


def test_password_change_wrong_current_password_is_generic(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    client, dispatcher = _build_api_client(auth_uow_factory, auth_test_database_url)
    client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    raw_verification = dispatcher.verification_deliveries[0].raw_token
    client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"verification_token": raw_verification.value},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    csrf = login.json()["csrf_token"]

    response = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "Wrong-Password-9", "new_password": OTHER_PASSWORD},
        headers={"Origin": TEST_ORIGIN, CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "authentication failed"
    assert client.get("/api/v1/auth/session").status_code == 200


def test_password_reset_request_unknown_email_is_generic(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    client, dispatcher = _build_api_client(auth_uow_factory, auth_test_database_url)
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "missing@example.test"},
    )
    assert response.status_code == 202
    assert response.json()["message"] == "request accepted"
    assert len(dispatcher.reset_deliveries) == 0


def test_logout_is_idempotent(auth_uow_factory: Any, auth_test_database_url: str) -> None:
    client, dispatcher = _build_api_client(auth_uow_factory, auth_test_database_url)
    client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    raw_verification = dispatcher.verification_deliveries[0].raw_token
    client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"verification_token": raw_verification.value},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    csrf = login.json()["csrf_token"]
    headers = {"Origin": TEST_ORIGIN, CSRF_HEADER_NAME: csrf}

    first = client.post("/api/v1/auth/logout", headers=headers)
    second = client.post("/api/v1/auth/logout", headers=headers)
    assert first.status_code == 204
    assert second.status_code == 204


def test_mfa_complete_rejects_disallowed_origin(
    auth_uow_factory: Any,
    auth_test_database_url: str,
) -> None:
    client, dispatcher = _build_api_client(
        auth_uow_factory,
        auth_test_database_url,
        mfa_required=True,
    )
    client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    raw_verification = dispatcher.verification_deliveries[0].raw_token
    client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"verification_token": raw_verification.value},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    csrf = login.json()["csrf_token"]

    response = client.post(
        "/api/v1/auth/mfa/complete",
        json={"method": "totp", "response": {"code": "123456"}},
        headers={"Origin": "http://evil.example.test", CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 403
