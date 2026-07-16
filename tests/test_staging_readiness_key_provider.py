"""Readiness checks for staging and production key-provider configuration."""

from __future__ import annotations

import os
from unittest.mock import patch

from closeros_api.observability_router import _managed_key_provider_status


def test_staging_readiness_accepts_sealed_static_keys() -> None:
    environment = {
        "APP_ENV": "staging",
        "STAGING_ENCRYPTION_KEY_HEX": "11" * 32,
        "STAGING_KNOWLEDGE_SEARCH_KEY_HEX": "22" * 32,
    }

    with patch.dict(os.environ, environment, clear=True):
        assert _managed_key_provider_status() == "configured"


def test_staging_readiness_rejects_missing_static_key() -> None:
    environment = {
        "APP_ENV": "staging",
        "STAGING_ENCRYPTION_KEY_HEX": "11" * 32,
    }

    with patch.dict(os.environ, environment, clear=True):
        assert _managed_key_provider_status() == "failed"


def test_production_readiness_still_requires_remote_kms() -> None:
    environment = {
        "APP_ENV": "production",
        "STAGING_ENCRYPTION_KEY_HEX": "11" * 32,
        "STAGING_KNOWLEDGE_SEARCH_KEY_HEX": "22" * 32,
    }

    with patch.dict(os.environ, environment, clear=True):
        assert _managed_key_provider_status() == "failed"


def test_production_readiness_accepts_complete_remote_kms_config() -> None:
    environment = {
        "APP_ENV": "production",
        "KMS_BASE_URL": "https://kms.example.com",
        "KMS_API_TOKEN_REF": "kms-token-ref",
        "KMS_ACTIVE_KEY_VERSION": "v1",
        "KMS_KEY_VERSIONS": "v1",
    }

    with patch.dict(os.environ, environment, clear=True):
        assert _managed_key_provider_status() == "configured"
