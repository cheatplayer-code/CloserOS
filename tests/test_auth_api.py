"""Unit tests for authentication API security and composition."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from closeros.application.authentication_workflows import AuthenticationWorkflowService
from closeros.security.authentication_tokens import RawAuthenticationToken
from closeros_api.app import create_app
from closeros_api.auth_ports import CaptureNotificationDispatcher, InMemoryRateLimiter
from closeros_api.auth_schemas import sanitize_validation_errors
from closeros_api.auth_security import (
    DEVELOPMENT_SESSION_COOKIE_NAME,
    PRODUCTION_SESSION_COOKIE_NAME,
    client_ip,
    csrf_token_is_valid,
    fingerprint_value,
    generate_csrf_token,
    read_session_cookie,
    session_cookie_config,
)
from closeros_api.composition import AuthRuntimeOverrides, build_auth_runtime
from closeros_api.settings import ApiConfigurationError, ApiSettings
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from starlette.requests import Request

from tests.auth_api_support import (
    TEST_CSRF_SECRET,
    TEST_ORIGIN,
    TEST_RATE_SECRET,
    TOKEN_ENTROPY_A,
    TOKEN_ENTROPY_B,
    deterministic_token_string,
    development_api_settings,
    production_api_settings,
)


def _workflows(service: object) -> AuthenticationWorkflowService:
    return cast(AuthenticationWorkflowService, service)


def test_production_settings_reject_http_origins() -> None:
    settings = ApiSettings(
        app_env="production",
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local",
        auth_allowed_origins=("http://insecure.example.test",),
        auth_csrf_secret=TEST_CSRF_SECRET,
        auth_rate_limit_secret=TEST_RATE_SECRET,
        session_touch_interval=timedelta(minutes=5),
        trust_forwarded_client_ip=False,
        webhook_max_body_bytes=1_048_576,
        csv_max_body_bytes=10_485_760,
        ingestion_service_id=UUID("00000000-0000-0000-0000-00000000e001"),
    )

    with pytest.raises(ApiConfigurationError):
        settings.validate_for_runtime()


def test_production_runtime_requires_explicit_adapters() -> None:
    settings = production_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )

    with pytest.raises(RuntimeError, match="MFA requirement policy"):
        build_auth_runtime(settings, AuthRuntimeOverrides())


def test_development_cookie_config_uses_dev_name() -> None:
    config = session_cookie_config(is_production=False)
    assert config.name == DEVELOPMENT_SESSION_COOKIE_NAME
    assert config.secure is False


def test_production_cookie_config_uses_host_prefix() -> None:
    config = session_cookie_config(is_production=True)
    assert config.name == PRODUCTION_SESSION_COOKIE_NAME
    assert config.secure is True


def test_csrf_token_is_bound_to_session_and_validates() -> None:
    token = RawAuthenticationToken(deterministic_token_string(TOKEN_ENTROPY_A))
    csrf = generate_csrf_token(session_token=token, secret=TEST_CSRF_SECRET)
    assert csrf_token_is_valid(
        session_token=token,
        secret=TEST_CSRF_SECRET,
        provided_token=csrf,
    )
    assert not csrf_token_is_valid(
        session_token=token,
        secret=TEST_CSRF_SECRET,
        provided_token="invalid-token-value",
    )


def test_fingerprint_does_not_echo_raw_input() -> None:
    digest = fingerprint_value(secret=TEST_RATE_SECRET, value="user@example.test")
    assert "user@example.test" not in digest
    assert digest


def test_sanitize_validation_errors_omit_input_values() -> None:
    sanitized = sanitize_validation_errors(
        [
            {
                "loc": ("body", "password"),
                "msg": "field required",
                "type": "missing",
                "input": "super-secret-value",
            }
        ]
    )

    assert sanitized == [
        {
            "location": "body.password",
            "message": "field required",
            "type": "missing",
        }
    ]
    assert "super-secret-value" not in str(sanitized)


def test_create_app_exposes_health_and_factory_injection() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    dispatcher = CaptureNotificationDispatcher()
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            notification_dispatcher=dispatcher,
            rate_limiter=InMemoryRateLimiter(),
            engine=None,
            session_factory=None,
            uow_factory=lambda: (_ for _ in ()).throw(RuntimeError("unused")),
            workflow_service=object(),  # type: ignore[arg-type]
        ),
    )

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_auth_modules_do_not_import_forbidden_libraries() -> None:
    forbidden = ("psycopg", "sqlalchemy")
    api_dir = Path("apps/api/src/closeros_api")
    for path in api_dir.glob("auth_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not any(name.startswith(forbidden) for name in imports)


def test_login_json_never_contains_raw_session_token() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )

    class FakeWorkflows:
        async def login_with_password(self, **kwargs: object) -> object:
            from datetime import UTC, datetime

            from closeros.application.authentication_issuance import IssuedAuthenticationSession
            from closeros.domain.authentication import (
                AuthenticationAssuranceLevel,
                AuthenticationSessionStage,
                AuthenticationTokenHash,
            )
            from closeros.domain.authentication_session import AuthenticationSession

            raw = RawAuthenticationToken(deterministic_token_string(TOKEN_ENTROPY_A))
            now = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
            session = AuthenticationSession(
                id=UUID("00000000-0000-0000-0000-000000000100"),
                user_id=UUID("00000000-0000-0000-0000-000000000010"),
                token_hash=AuthenticationTokenHash(digest=bytes(range(32))),
                stage=AuthenticationSessionStage.AUTHENTICATED,
                assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
                mfa_completed=False,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(hours=12),
                revoked_at=None,
            )
            return IssuedAuthenticationSession(session=session, raw_token=raw)

    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(FakeWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app, base_url="http://testserver") as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.test", "password": "Synthetic-Password-1"},
        )

    raw_token_str = deterministic_token_string(TOKEN_ENTROPY_A)
    assert raw_token_str not in response.text


def test_production_login_sets_secure_host_cookie() -> None:
    settings = production_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )

    class FakeWorkflows:
        async def login_with_password(self, **kwargs: object) -> object:
            from datetime import UTC, datetime

            from closeros.application.authentication_issuance import IssuedAuthenticationSession
            from closeros.domain.authentication import (
                AuthenticationAssuranceLevel,
                AuthenticationSessionStage,
                AuthenticationTokenHash,
            )
            from closeros.domain.authentication_session import AuthenticationSession

            raw = RawAuthenticationToken(deterministic_token_string(TOKEN_ENTROPY_A))
            now = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
            session = AuthenticationSession(
                id=uuid4(),
                user_id=uuid4(),
                token_hash=AuthenticationTokenHash(digest=bytes(range(32))),
                stage=AuthenticationSessionStage.AUTHENTICATED,
                assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
                mfa_completed=False,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(hours=12),
                revoked_at=None,
            )
            return IssuedAuthenticationSession(session=session, raw_token=raw)

    from closeros.application.provider_adapter_registry import ProviderAdapterRegistry
    from closeros.infrastructure.in_memory_webhook_rate_limiter import InMemoryWebhookRateLimiter
    from closeros.infrastructure.noop_import_content_scanner import NoOpImportContentScanner

    from tests.encryption_support import build_test_key_provider

    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(FakeWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
            mfa_requirement_policy=_AlwaysFalseMfaPolicy(),
            key_provider=build_test_key_provider(),
            adapter_registry=ProviderAdapterRegistry(),
            webhook_rate_limiter=InMemoryWebhookRateLimiter(),
            content_scanner=NoOpImportContentScanner(),
            engine=None,
            session_factory=None,
        ),
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.test", "password": "Synthetic-Password-1"},
        )

    set_cookie = response.headers.get("set-cookie", "")
    assert PRODUCTION_SESSION_COOKIE_NAME in set_cookie
    assert "Secure" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Domain=" not in set_cookie


def test_validation_error_response_has_security_headers() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(_NoopWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/auth/login", json={"email": "not-an-email"})

    assert response.status_code == 422
    assert response.headers["Cache-Control"] == "no-store"
    assert "password" not in response.text.lower() or "validation failed" in response.text


def test_register_always_returns_accepted() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    dispatcher = CaptureNotificationDispatcher()
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(_DuplicateRegisterWorkflows()),
            notification_dispatcher=dispatcher,
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "user@example.test", "password": "Synthetic-Password-1"},
        )

    assert response.status_code == 202
    assert response.json()["message"] == "request accepted"


def test_rate_limiter_returns_generic_429() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    limiter = InMemoryRateLimiter()
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(_DuplicateRegisterWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=limiter,
        ),
    )

    with TestClient(app) as client:
        for _ in range(6):
            response = client.post(
                "/api/v1/auth/register",
                json={"email": "user@example.test", "password": "Synthetic-Password-1"},
            )
        assert response.status_code == 429
        assert response.json()["detail"] == "too many requests"
        assert "Retry-After" in response.headers


def test_cors_uses_exact_origins_not_wildcard() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(_NoopWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app) as client:
        response = client.options(
            "/api/v1/auth/session",
            headers={
                "Origin": TEST_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.headers.get("access-control-allow-origin") == TEST_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_client_ip_ignores_spoofed_forwarded_header_by_default() -> None:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"x-forwarded-for", b"203.0.113.50")],
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)
    assert client_ip(request, trust_forwarded_client_ip=False) == "127.0.0.1"


def test_client_ip_honors_forwarded_header_when_trusted() -> None:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"x-forwarded-for", b"203.0.113.50, 10.0.0.1")],
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)
    assert client_ip(request, trust_forwarded_client_ip=True) == "203.0.113.50"


def test_origin_is_allowed_requires_exact_match() -> None:
    from closeros_api.auth_security import origin_is_allowed

    allowed = ("http://127.0.0.1:3000",)
    assert origin_is_allowed(origin=TEST_ORIGIN, allowed_origins=allowed)
    assert not origin_is_allowed(origin="http://evil.example.test", allowed_origins=allowed)
    assert not origin_is_allowed(origin=None, allowed_origins=allowed)


def test_read_session_cookie_rejects_malformed_value() -> None:
    config = session_cookie_config(is_production=False)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"cookie", f"{config.name}=not-a-valid-token".encode())],
    }
    request = Request(scope)
    assert read_session_cookie(request, cookie_config=config) is None


def test_register_request_rejects_unknown_fields() -> None:
    from closeros_api.auth_schemas import RegisterRequest

    with pytest.raises(ValidationError):
        RegisterRequest(
            email="user@example.test",
            password=SecretStr("Synthetic-Password-1"),
            mfa_required=True,  # type: ignore[call-arg]
        )


def test_register_request_password_hidden_from_repr() -> None:
    from closeros_api.auth_schemas import RegisterRequest

    request = RegisterRequest(email="user@example.test", password=SecretStr("Synthetic-Password-1"))
    assert "Synthetic-Password-1" not in repr(request)


def test_production_runtime_requires_notification_dispatcher() -> None:
    settings = production_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )

    class Policy:
        async def requires_mfa_for_user(self, *, user_id: UUID) -> bool:
            return False

    with pytest.raises(RuntimeError, match="notification dispatcher"):
        build_auth_runtime(
            settings,
            AuthRuntimeOverrides(mfa_requirement_policy=Policy()),
        )


def test_production_runtime_requires_rate_limiter() -> None:
    settings = production_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )

    class Policy:
        async def requires_mfa_for_user(self, *, user_id: UUID) -> bool:
            return False

    class Dispatcher:
        async def dispatch_email_verification(self, delivery: object) -> None:
            return None

        async def dispatch_password_reset(self, delivery: object) -> None:
            return None

    with pytest.raises(RuntimeError, match="rate limiter"):
        build_auth_runtime(
            settings,
            AuthRuntimeOverrides(
                mfa_requirement_policy=Policy(),
                notification_dispatcher=Dispatcher(),
            ),
        )


def test_logout_rejects_invalid_csrf() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(_NoopWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app) as client:
        client.cookies.set(
            DEVELOPMENT_SESSION_COOKIE_NAME, deterministic_token_string(TOKEN_ENTROPY_A)
        )
        response = client.post(
            "/api/v1/auth/logout",
            headers={"Origin": TEST_ORIGIN, "X-CSRF-Token": "invalid"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "access denied"


def test_logout_rejects_disallowed_origin() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    token = RawAuthenticationToken(deterministic_token_string(TOKEN_ENTROPY_A))
    csrf = generate_csrf_token(session_token=token, secret=TEST_CSRF_SECRET)
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(_NoopWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app) as client:
        client.cookies.set(DEVELOPMENT_SESSION_COOKIE_NAME, token.value)
        response = client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "http://evil.example.test", "X-CSRF-Token": csrf},
        )

    assert response.status_code == 403


def test_logout_clears_cookie_without_session() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(_NoopWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert DEVELOPMENT_SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")


def test_session_without_cookie_returns_generic_401() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(_NoopWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/auth/session")

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication failed"


def test_password_reset_request_always_returns_accepted() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )

    class ResetWorkflows:
        async def request_password_reset(self, **kwargs: object) -> object:
            from closeros.application.authentication_workflows import (
                AuthenticationRequestAccepted,
            )

            return AuthenticationRequestAccepted()

    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(ResetWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "missing@example.test"},
        )

    assert response.status_code == 202
    assert response.json()["message"] == "request accepted"


def test_verification_confirm_invalid_token_is_generic() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(_NoopWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/email-verification/confirm",
            json={"verification_token": deterministic_token_string(TOKEN_ENTROPY_A)},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "request unavailable"


def test_login_failure_returns_generic_401() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )

    class FailingLoginWorkflows:
        async def login_with_password(self, **kwargs: object) -> object:
            from closeros.application.authentication_workflows import AuthenticationFailedError

            raise AuthenticationFailedError()

    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(FailingLoginWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.test", "password": "Synthetic-Password-1"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication failed"
    assert "Synthetic-Password-1" not in response.text


def test_register_dispatches_verification_only_for_eligible_delivery() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    dispatcher = CaptureNotificationDispatcher()
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(_AcceptingRegisterWorkflows()),
            notification_dispatcher=dispatcher,
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "user@example.test", "password": "Synthetic-Password-1"},
        )

    assert response.status_code == 202
    assert len(dispatcher.verification_deliveries) == 1
    assert deterministic_token_string(TOKEN_ENTROPY_B) not in response.text


def test_auth_responses_include_cache_control_headers() -> None:
    settings = development_api_settings(
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local"
    )
    app = create_app(
        settings=settings,
        overrides=AuthRuntimeOverrides(
            workflow_service=_workflows(_NoopWorkflows()),
            notification_dispatcher=CaptureNotificationDispatcher(),
            rate_limiter=InMemoryRateLimiter(),
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/email-verification/request",
            json={"email": "user@example.test"},
        )

    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_development_settings_reject_weak_production_secrets() -> None:
    settings = ApiSettings(
        app_env="production",
        database_url="postgresql://user:secret@127.0.0.1:5432/closeros_local",
        auth_allowed_origins=("https://app.example.test",),
        auth_csrf_secret=b"short",
        auth_rate_limit_secret=TEST_RATE_SECRET,
        session_touch_interval=timedelta(minutes=5),
        trust_forwarded_client_ip=False,
        webhook_max_body_bytes=1_048_576,
        csv_max_body_bytes=10_485_760,
        ingestion_service_id=UUID("00000000-0000-0000-0000-00000000e001"),
    )

    with pytest.raises(ApiConfigurationError, match="CSRF"):
        settings.validate_for_runtime()


class _AlwaysFalseMfaPolicy:
    async def requires_mfa_for_user(self, *, user_id: UUID) -> bool:
        return False


class _NoopWorkflows:
    async def register_user(self, **kwargs: object) -> object:
        raise RuntimeError("not implemented")

    async def login_with_password(self, **kwargs: object) -> object:
        raise RuntimeError("not implemented")

    async def confirm_email_verification(self, **kwargs: object) -> None:
        from closeros.application.authentication_workflows import (
            AuthenticationWorkflowUnavailableError,
        )

        raise AuthenticationWorkflowUnavailableError()

    async def request_email_verification(self, **kwargs: object) -> object:
        from closeros.application.authentication_workflows import (
            AuthenticationRequestAccepted,
        )

        return AuthenticationRequestAccepted()


class _DuplicateRegisterWorkflows:
    async def register_user(self, **kwargs: object) -> object:
        from closeros.application.authentication_workflows import RegistrationUnavailableError

        raise RegistrationUnavailableError()


class _AcceptingRegisterWorkflows:
    async def register_user(self, **kwargs: object) -> object:
        from closeros.application.authentication_workflows import (
            AuthenticationNotificationDelivery,
            RegistrationResult,
        )
        from closeros.domain.authentication import AuthenticationEmail
        from closeros.security.authentication_tokens import RawAuthenticationToken

        return RegistrationResult(
            user_id=UUID("00000000-0000-0000-0000-000000000010"),
            delivery=AuthenticationNotificationDelivery(
                recipient=AuthenticationEmail("user@example.test"),
                raw_token=RawAuthenticationToken(deterministic_token_string(TOKEN_ENTROPY_B)),
            ),
        )
