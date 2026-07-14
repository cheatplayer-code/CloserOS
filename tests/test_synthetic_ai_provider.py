"""Unit tests for synthetic AI provider."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from closeros.application.ai_ports import ProviderRequest
from closeros.application.synthetic_ai_provider import SyntheticAiProvider, SyntheticProviderError
from closeros.domain.ai_analysis import AiProviderCode, AiPurpose


def _request(*, purpose: AiPurpose = AiPurpose.CONVERSATION_ANALYSIS) -> ProviderRequest:
    return ProviderRequest(
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        provider_code=AiProviderCode.SYNTHETIC,
        purpose=purpose,
        model_code="synthetic-model",
        prompt_version="nopq-prompt-v1",
        rubric_version="nopq-rubric-v1",
        prompt_text="synthetic sanitized prompt",
        evidence_message_ids=(UUID("00000000-0000-0000-0000-000000000100"),),
        max_output_characters=8_192,
        input_digest=bytes(range(32)),
        requested_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
    )


def test_provider_returns_valid_json_finding_payload() -> None:
    async def exercise() -> None:
        provider = SyntheticAiProvider()
        result = await provider.call_chat_json(request=_request(), bearer_key="unused")
        payload = json.loads(result.output_text)
        assert payload["purpose"] == "conversation.analysis"
        assert payload["findings"][0]["issue_code"] == "missing_next_step"
        assert payload["findings"][0]["evidence_message_ids"]
        assert result.provider_code is AiProviderCode.SYNTHETIC

    asyncio.run(exercise())


def test_provider_rejects_unsupported_purpose() -> None:
    async def exercise() -> None:
        provider = SyntheticAiProvider()
        with pytest.raises(SyntheticProviderError, match="not supported"):
            await provider.call_chat_json(
                request=_request(purpose=AiPurpose.CONVERSATION_SUMMARY),
                bearer_key="unused",
            )

    asyncio.run(exercise())


def test_provider_requires_evidence_message_ids() -> None:
    async def exercise() -> None:
        provider = SyntheticAiProvider()
        req = _request()
        req = ProviderRequest(
            tenant_id=req.tenant_id,
            provider_code=req.provider_code,
            purpose=req.purpose,
            model_code=req.model_code,
            prompt_version=req.prompt_version,
            rubric_version=req.rubric_version,
            prompt_text=req.prompt_text,
            evidence_message_ids=(),
            max_output_characters=req.max_output_characters,
            input_digest=req.input_digest,
            requested_at=req.requested_at,
        )
        with pytest.raises(SyntheticProviderError, match="requires evidence"):
            await provider.call_chat_json(request=req, bearer_key="unused")

    asyncio.run(exercise())


def test_provider_sets_zero_cost_usage_for_ci_friendly_calls() -> None:
    async def exercise() -> None:
        provider = SyntheticAiProvider()
        result = await provider.call_chat_json(request=_request(), bearer_key="unused")
        assert result.usage is not None
        assert result.usage.estimated_cost_microunits == 0
        assert result.usage.input_tokens > 0
        assert result.usage.output_tokens > 0

    asyncio.run(exercise())
