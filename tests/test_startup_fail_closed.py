"""Tests proving the API fails closed on production misconfiguration."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from closeros_api.settings import ApiConfigurationError, ApiSettings

from tests.auth_api_support import production_api_settings
from tests.database_url_support import placeholder_database_url


def test_create_app_rejects_missing_database_url() -> None:
    with (
        patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False),
        pytest.raises(ApiConfigurationError, match="DATABASE_URL"),
    ):
        ApiSettings.from_env()


def test_create_app_rejects_production_without_explicit_runtime_dependencies() -> None:
    from closeros_api.app import create_app

    settings = production_api_settings(database_url=placeholder_database_url())
    with pytest.raises(RuntimeError, match="REDIS_URL|KMS_BASE_URL|CRM_ENABLED|CLAMAV"):
        create_app(settings=settings)


def test_create_app_rejects_production_http_origins() -> None:
    from closeros_api.app import create_app

    settings = ApiSettings(
        app_env="production",
        database_url=placeholder_database_url(),
        auth_allowed_origins=("http://app.example.test",),
        auth_csrf_secret=b"production_csrf_secret_value_32b",
        auth_rate_limit_secret=b"production_rate_secret_value_32b",
        session_touch_interval=production_api_settings(
            database_url=placeholder_database_url()
        ).session_touch_interval,
        trust_forwarded_client_ip=False,
        webhook_max_body_bytes=1_048_576,
        csv_max_body_bytes=10_485_760,
        ingestion_service_id=production_api_settings(
            database_url=placeholder_database_url()
        ).ingestion_service_id,
    )
    with pytest.raises(ApiConfigurationError, match="https"):
        create_app(settings=settings)
