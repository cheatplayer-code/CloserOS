"""Unit tests for OpenAI-compatible adapter with mocked HTTPX transport."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from closeros.application.ai_ports import ProviderRequest
from closeros.application.openai_compatible_adapter import (
    OpenAICompatibleAdapterError,
    OpenAICompatibleChatAdapter,
)
from closeros.domain.ai_analysis import AiProviderCode, AiPurpose


def _request(*, max_chars: int = 500) -> ProviderRequest:
    return ProviderRequest(
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        provider_code=AiProviderCode.OPENAI_COMPATIBLE,
        purpose=AiPurpose.CONVERSATION_ANALYSIS,
        model_code="deepseek-v4-flash",
        prompt_version="nopq-prompt-v1",
        rubric_version="nopq-rubric-v1",
        prompt_text="synthetic sanitized prompt",
        evidence_message_ids=(UUID("00000000-0000-0000-0000-000000000101"),),
        max_output_characters=max_chars,
        input_digest=bytes(range(32)),
        requested_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
    )


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


def test_adapter_rejects_non_https_base_url() -> None:
    with pytest.raises(ValueError, match="https"):
        OpenAICompatibleChatAdapter(base_url="http://api.synthetic.invalid")


def test_adapter_rejects_missing_bearer_key() -> None:
    async def exercise() -> None:
        adapter = OpenAICompatibleChatAdapter(
            base_url="https://api.synthetic.invalid",
            _client=_client(httpx.MockTransport(lambda req: httpx.Response(200, json={}))),
        )
        with pytest.raises(OpenAICompatibleAdapterError, match="missing"):
            await adapter.call_chat_json(request=_request(), bearer_key=" ")

    asyncio.run(exercise())


def test_adapter_successfully_parses_valid_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        payload = {
            "choices": [
                {"message": {"content": '{"purpose":"conversation.analysis","findings":[]}'}}
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8},
        }
        return httpx.Response(200, content=json.dumps(payload).encode("utf-8"))

    async def exercise() -> None:
        adapter = OpenAICompatibleChatAdapter(
            base_url="https://api.synthetic.invalid",
            _client=_client(httpx.MockTransport(handler)),
        )
        result = await adapter.call_chat_json(request=_request(), bearer_key="synthetic-token")
        assert result.output_text == '{"purpose":"conversation.analysis","findings":[]}'
        assert result.usage is not None
        assert result.usage.input_tokens == 12
        assert result.usage.output_tokens == 8

    asyncio.run(exercise())


def test_adapter_rejects_non_success_status() -> None:
    async def exercise() -> None:
        adapter = OpenAICompatibleChatAdapter(
            base_url="https://api.synthetic.invalid",
            _client=_client(
                httpx.MockTransport(lambda req: httpx.Response(429, text="rate limit"))
            ),
        )
        with pytest.raises(OpenAICompatibleAdapterError, match="non-success"):
            await adapter.call_chat_json(request=_request(), bearer_key="synthetic-token")

    asyncio.run(exercise())


def test_adapter_rejects_oversized_response_bytes() -> None:
    async def exercise() -> None:
        payload = b"x" * 5_000
        adapter = OpenAICompatibleChatAdapter(
            base_url="https://api.synthetic.invalid",
            max_response_bytes=64,
            _client=_client(httpx.MockTransport(lambda req: httpx.Response(200, content=payload))),
        )
        with pytest.raises(OpenAICompatibleAdapterError, match="byte limit"):
            await adapter.call_chat_json(request=_request(), bearer_key="synthetic-token")

    asyncio.run(exercise())


def test_adapter_rejects_invalid_json_body() -> None:
    async def exercise() -> None:
        adapter = OpenAICompatibleChatAdapter(
            base_url="https://api.synthetic.invalid",
            _client=_client(httpx.MockTransport(lambda req: httpx.Response(200, content=b"{bad"))),
        )
        with pytest.raises(OpenAICompatibleAdapterError, match="invalid json"):
            await adapter.call_chat_json(request=_request(), bearer_key="synthetic-token")

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
    ],
)
def test_adapter_rejects_missing_choice_message_content(payload: dict[str, object]) -> None:
    async def exercise() -> None:
        adapter = OpenAICompatibleChatAdapter(
            base_url="https://api.synthetic.invalid",
            _client=_client(
                httpx.MockTransport(
                    lambda req: httpx.Response(200, content=json.dumps(payload).encode("utf-8"))
                )
            ),
        )
        with pytest.raises(OpenAICompatibleAdapterError):
            await adapter.call_chat_json(request=_request(), bearer_key="synthetic-token")

    asyncio.run(exercise())


def test_adapter_rejects_output_longer_than_requested_limit() -> None:
    content = "x" * 128

    def handler(_: httpx.Request) -> httpx.Response:
        payload = {"choices": [{"message": {"content": content}}]}
        return httpx.Response(200, content=json.dumps(payload).encode("utf-8"))

    async def exercise() -> None:
        adapter = OpenAICompatibleChatAdapter(
            base_url="https://api.synthetic.invalid",
            _client=_client(httpx.MockTransport(handler)),
        )
        with pytest.raises(OpenAICompatibleAdapterError, match="character limit"):
            await adapter.call_chat_json(
                request=_request(max_chars=32), bearer_key="synthetic-token"
            )

    asyncio.run(exercise())


def test_adapter_defaults_usage_to_zero_when_usage_block_missing() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        payload = {
            "choices": [
                {"message": {"content": '{"purpose":"conversation.analysis","findings":[]}'}}
            ]
        }
        return httpx.Response(200, content=json.dumps(payload).encode("utf-8"))

    async def exercise() -> None:
        adapter = OpenAICompatibleChatAdapter(
            base_url="https://api.synthetic.invalid",
            _client=_client(httpx.MockTransport(handler)),
        )
        result = await adapter.call_chat_json(request=_request(), bearer_key="synthetic-token")
        assert result.usage is not None
        assert result.usage.input_tokens == 0
        assert result.usage.output_tokens == 0

    asyncio.run(exercise())


def test_adapter_rejects_transport_errors() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    async def exercise() -> None:
        adapter = OpenAICompatibleChatAdapter(
            base_url="https://api.synthetic.invalid",
            _client=_client(httpx.MockTransport(handler)),
        )
        with pytest.raises(OpenAICompatibleAdapterError, match="request failed"):
            await adapter.call_chat_json(request=_request(), bearer_key="synthetic-token")

    asyncio.run(exercise())
