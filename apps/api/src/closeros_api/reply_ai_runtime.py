"""Fail-closed provider selection for the synchronous Reply Copilot path."""

from __future__ import annotations

from dataclasses import dataclass

from closeros.application.ai_ports import AiCredentialResolver, AiProvider
from closeros.application.openai_compatible_adapter import OpenAICompatibleChatAdapter
from closeros.application.synthetic_ai_provider import SyntheticAiProvider
from closeros.domain.ai_analysis import AiProviderCode
from closeros.infrastructure.configured_ai_credential_resolver import (
    ConfiguredAiCredentialResolver,
)

from closeros_api.settings import ApiConfigurationError, ApiSettings

_SYNTHETIC_REPLY_MODEL = "synthetic-reply-v1"


@dataclass(frozen=True, slots=True)
class ReplyAiRuntimeConfiguration:
    provider: AiProvider | None
    credential_resolver: AiCredentialResolver | None
    model_code: str | None


def build_reply_ai_runtime(settings: ApiSettings) -> ReplyAiRuntimeConfiguration:
    """Select deterministic, live, or disabled behavior without silent fallback."""

    if settings.ai_external_calls_enabled:
        if settings.deepseek_api_key is None:
            raise ApiConfigurationError(
                "AI_EXTERNAL_CALLS_ENABLED requires DEEPSEEK_API_KEY"
            )
        if settings.deepseek_model is None:
            raise ApiConfigurationError(
                "AI_EXTERNAL_CALLS_ENABLED requires DEEPSEEK_MODEL"
            )
        return ReplyAiRuntimeConfiguration(
            provider=OpenAICompatibleChatAdapter(
                base_url=settings.deepseek_base_url,
                provider_code=AiProviderCode.OPENAI_COMPATIBLE,
            ),
            credential_resolver=ConfiguredAiCredentialResolver(
                bearer_key=settings.deepseek_api_key,
            ),
            model_code=settings.deepseek_model,
        )

    if settings.is_development:
        return ReplyAiRuntimeConfiguration(
            provider=SyntheticAiProvider(),
            credential_resolver=None,
            model_code=_SYNTHETIC_REPLY_MODEL,
        )

    return ReplyAiRuntimeConfiguration(
        provider=None,
        credential_resolver=None,
        model_code=None,
    )


__all__ = ["ReplyAiRuntimeConfiguration", "build_reply_ai_runtime"]
