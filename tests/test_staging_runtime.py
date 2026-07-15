"""Tests for managed staging composition without production KMS fallback."""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from closeros.infrastructure.staging_runtime import (
    StagingConfigurationError,
    build_staging_key_provider_from_env,
    build_staging_knowledge_search_key_provider_from_env,
    build_staging_shared_runtime,
)
from closeros_api.composition import build_api_runtime
from closeros_api.observability_router import ProductionReadinessProbe
from closeros_api.settings import ApiConfigurationError, ApiSettings
from closeros_worker.runtime import build_worker_runtime
from closeros_worker.settings import WorkerSettings

from tests.database_url_support import placeholder_database_url


def _staging_environment() -> dict[str, str]:
    return {
        "APP_ENV": "staging",
        "DATABASE_URL": placeholder_database_url(),
        "REDIS_URL": "redis://default:staging-password@redis.railway.internal:6379/0",
        "REDIS_RATE_LIMIT_HMAC_SECRET": "h" * 48,
        "STAGING_ENCRYPTION_KEY_HEX": "11" * 32,
        "STAGING_ENCRYPTION_KEY_VERSION": "staging-kek-v1",
        "STAGING_KNOWLEDGE_SEARCH_KEY_HEX": "22" * 32,
        "AUTH_ALLOWED_ORIGINS": "https://web-staging.example.com",
        "AUTH_CSRF_SECRET": "c" * 48,
        "AUTH_RATE_LIMIT_SECRET": "r" * 48,
        "INGESTION_SERVICE_ID": "7f53206e-9b57-49cc-9f79-3c3f3a750dfa",
        "WHATSAPP_ENABLED": "false",
        "CRM_ENABLED": "false",
        "NOTIFICATIONS_ENABLED": "false",
        "MEDIA_SCANNER_ENABLED": "false",
        "AI_EXTERNAL_CALLS_ENABLED": "false",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com/",
        "DEEPSEEK_MODEL": "deepseek-v4-flash",
    }


def _staging_api_settings() -> ApiSettings:
    return ApiSettings(
        app_env="staging",
        database_url=placeholder_database_url(),
        auth_allowed_origins=("https://web-staging.example.com",),
        auth_csrf_secret=b"c" * 48,
        auth_rate_limit_secret=b"r" * 48,
        session_touch_interval=timedelta(minutes=5),
        trust_forwarded_client_ip=False,
        webhook_max_body_bytes=1_048_576,
        csv_max_body_bytes=10_485_760,
        ingestion_service_id=UUID("7f53206e-9b57-49cc-9f79-3c3f3a750dfa"),
    )


def test_api_settings_accept_explicit_staging_with_secure_origins() -> None:
    settings = _staging_api_settings()

    settings.validate_for_runtime()

    assert settings.is_staging is True
    assert settings.is_managed is True
    assert settings.is_production is False
    assert settings.is_development is False


def test_api_settings_reject_staging_http_origin() -> None:
    settings = _staging_api_settings()
    settings = ApiSettings(
        app_env=settings.app_env,
        database_url=settings.database_url,
        auth_allowed_origins=("http://web-staging.example.com",),
        auth_csrf_secret=settings.auth_csrf_secret,
        auth_rate_limit_secret=settings.auth_rate_limit_secret,
        session_touch_interval=settings.session_touch_interval,
        trust_forwarded_client_ip=settings.trust_forwarded_client_ip,
        webhook_max_body_bytes=settings.webhook_max_body_bytes,
        csv_max_body_bytes=settings.csv_max_body_bytes,
        ingestion_service_id=settings.ingestion_service_id,
    )

    with pytest.raises(ApiConfigurationError, match="https"):
        settings.validate_for_runtime()


def test_staging_key_providers_use_sealed_hex_material_without_repr_leak() -> None:
    environment = _staging_environment()
    with patch.dict(os.environ, environment, clear=True):
        encryption = build_staging_key_provider_from_env()
        search = build_staging_knowledge_search_key_provider_from_env()

    assert encryption.active_key_version == "staging-kek-v1"
    assert encryption.list_key_versions() == ("staging-kek-v1",)
    assert "11" * 32 not in repr(encryption)
    assert search.key_for_tenant(tenant_id=uuid4()) == bytes.fromhex("22" * 32)
    assert "22" * 32 not in repr(search)


def test_staging_key_provider_rejects_invalid_hex() -> None:
    environment = _staging_environment()
    environment["STAGING_ENCRYPTION_KEY_HEX"] = "invalid"

    with (
        patch.dict(os.environ, environment, clear=True),
        pytest.raises(StagingConfigurationError, match="64 hexadecimal"),
    ):
        build_staging_key_provider_from_env()


def test_staging_shared_runtime_does_not_require_production_kms() -> None:
    environment = _staging_environment()
    with patch.dict(os.environ, environment, clear=True):
        runtime = build_staging_shared_runtime(
            database_url=placeholder_database_url()
        )

    assert runtime.key_provider.active_key_version == "staging-kek-v1"
    assert runtime.capabilities.external_ai_enabled is False
    assert "KMS_BASE_URL" not in environment

    async def close() -> None:
        await runtime.redis.aclose()
        await runtime.engine.dispose()

    asyncio.run(close())


def test_staging_api_runtime_uses_secure_cookie_and_managed_readiness() -> None:
    environment = _staging_environment()
    with patch.dict(os.environ, environment, clear=True):
        runtime = build_api_runtime(_staging_api_settings())

    assert runtime.cookie_config.secure is True
    assert runtime.cookie_config.name == "__Host-closeros_session"
    assert isinstance(runtime.readiness_probe, ProductionReadinessProbe)
    assert runtime.capabilities is not None
    assert runtime.capabilities.external_ai_enabled is False

    async def close() -> None:
        if hasattr(runtime.rate_limiter, "redis"):
            await runtime.rate_limiter.redis.aclose()
        await runtime.dispose()

    asyncio.run(close())


def test_staging_worker_runtime_uses_managed_dependencies() -> None:
    environment = _staging_environment()
    with patch.dict(os.environ, environment, clear=True):
        settings = WorkerSettings.from_env()
        runtime = build_worker_runtime(settings)

    assert settings.is_staging is True
    assert settings.is_managed is True
    assert runtime.capabilities is not None
    assert runtime.capabilities.external_ai_enabled is False

    asyncio.run(runtime.dispose())
