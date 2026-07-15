"""Focused tests for fail-closed Reply Copilot provider selection."""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

import pytest
from closeros.application.openai_compatible_adapter import OpenAICompatibleChatAdapter
from closeros.application.synthetic_ai_provider import SyntheticAiProvider
from closeros.domain.ai_analysis import AiProviderCode
from closeros_api.reply_ai_runtime import build_reply_ai_runtime
from closeros_api.settings import ApiConfigurationError, ApiSettings

from tests.auth_api_support import development_api_settings, production_api_settings
from tests.database_url_support import placeholder_database_url


def test_disabled_development_uses_deterministic_synthetic_provider() -> None:
    settings = development_api_settings(database_url=placeholder_database_url())

    runtime = build_reply_ai_runtime(settings)

    assert isinstance(runtime.provider, SyntheticAiProvider)
    assert runtime.credential_resolver is None
    assert runtime.model_code == "synthetic-reply-v1"


def test_disabled_production_does_not_silently_fallback_to_synthetic() -> None:
    settings = production_api_settings(database_url=placeholder_database_url())

    runtime = build_reply_ai_runtime(settings)

    assert runtime.provider is None
    assert runtime.credential_resolver is None
    assert runtime.model_code is None


def test_enabled_runtime_uses_configured_deepseek_adapter_and_hidden_key() -> None:
    secret = "synthetic-deepseek-secret"
    settings = replace(
        development_api_settings(database_url=placeholder_database_url()),
        ai_external_calls_enabled=True,
        deepseek_api_key=secret,
        deepseek_base_url="https://api.deepseek.com/",
        deepseek_model="deepseek-v4-flash",
    )
    settings.validate_for_runtime()

    runtime = build_reply_ai_runtime(settings)

    assert isinstance(runtime.provider, OpenAICompatibleChatAdapter)
    assert runtime.provider.base_url == "https://api.deepseek.com/"
    assert runtime.provider.provider_code is AiProviderCode.OPENAI_COMPATIBLE
    assert runtime.model_code == "deepseek-v4-flash"
    assert runtime.credential_resolver is not None
    resolved = asyncio.run(
        runtime.credential_resolver.resolve_bearer_key(
            tenant_id=uuid4(),
            provider_code=AiProviderCode.OPENAI_COMPATIBLE,
        )
    )
    assert resolved == secret
    assert secret not in repr(runtime.credential_resolver)
    assert secret not in repr(settings)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"deepseek_api_key": None}, "DEEPSEEK_API_KEY"),
        ({"deepseek_model": None}, "DEEPSEEK_MODEL"),
        ({"deepseek_base_url": "http://api.deepseek.com/"}, "HTTPS"),
    ],
)
def test_enabled_runtime_configuration_fails_closed(
    changes: dict[str, object],
    message: str,
) -> None:
    base = replace(
        development_api_settings(database_url=placeholder_database_url()),
        ai_external_calls_enabled=True,
        deepseek_api_key="synthetic-key",
        deepseek_base_url="https://api.deepseek.com/",
        deepseek_model="deepseek-v4-flash",
    )
    settings = replace(base, **changes)

    with pytest.raises(ApiConfigurationError, match=message):
        settings.validate_for_runtime()


def test_from_env_rejects_ambiguous_external_ai_boolean() -> None:
    with (
        patch.dict(
            os.environ,
            {
                "DATABASE_URL": placeholder_database_url(),
                "AI_EXTERNAL_CALLS_ENABLED": "sometimes",
            },
            clear=True,
        ),
        pytest.raises(ApiConfigurationError, match="AI_EXTERNAL_CALLS_ENABLED"),
    ):
        ApiSettings.from_env()
