"""HTTPX-based OpenAI-compatible provider adapter without SDK dependency."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import httpx

from closeros.application.ai_ports import AiProvider, ProviderRequest, ProviderResult
from closeros.domain.ai_analysis import AiProviderCode, AiUsage

_DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
_DEFAULT_READ_TIMEOUT_SECONDS = 20.0
_DEFAULT_WRITE_TIMEOUT_SECONDS = 10.0
_DEFAULT_POOL_TIMEOUT_SECONDS = 5.0
_MIN_OUTPUT_TOKENS = 1
_MAX_OUTPUT_TOKENS = 4_096
_MAX_RESPONSE_BYTES = 256 * 1024


class OpenAICompatibleAdapterError(Exception):
    """Raised when an OpenAI-compatible provider call fails safely."""


def _validate_https_base_url(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    parsed = urlparse(normalized)
    if parsed.scheme != "https":
        raise ValueError(f"{field_name} must use https")
    if not parsed.netloc:
        raise ValueError(f"{field_name} must include a host")
    return normalized if normalized.endswith("/") else f"{normalized}/"


def _validate_non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _extract_usage(payload: object, *, latency_milliseconds: int) -> AiUsage:
    if not isinstance(payload, dict):
        return AiUsage(
            input_tokens=0,
            output_tokens=0,
            latency_milliseconds=latency_milliseconds,
            estimated_cost_microunits=0,
        )
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return AiUsage(
            input_tokens=0,
            output_tokens=0,
            latency_milliseconds=latency_milliseconds,
            estimated_cost_microunits=0,
        )
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    if type(prompt_tokens) is not int:
        prompt_tokens = 0
    if type(completion_tokens) is not int:
        completion_tokens = 0
    return AiUsage(
        input_tokens=max(prompt_tokens, 0),
        output_tokens=max(completion_tokens, 0),
        latency_milliseconds=latency_milliseconds,
        estimated_cost_microunits=0,
    )


@dataclass(frozen=True, slots=True)
class OpenAICompatibleChatAdapter(AiProvider):
    """Provider-neutral adapter for OpenAI-compatible chat completion APIs."""

    base_url: str
    provider_code: AiProviderCode = AiProviderCode.OPENAI_COMPATIBLE
    connect_timeout_seconds: float = _DEFAULT_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = _DEFAULT_READ_TIMEOUT_SECONDS
    write_timeout_seconds: float = _DEFAULT_WRITE_TIMEOUT_SECONDS
    pool_timeout_seconds: float = _DEFAULT_POOL_TIMEOUT_SECONDS
    max_response_bytes: int = _MAX_RESPONSE_BYTES
    _client: httpx.AsyncClient | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _validate_https_base_url(self.base_url, "base_url"))
        if not isinstance(self.provider_code, AiProviderCode):
            raise TypeError("provider_code must be an AiProviderCode")
        for field_name in (
            "connect_timeout_seconds",
            "read_timeout_seconds",
            "write_timeout_seconds",
            "pool_timeout_seconds",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, float):
                raise TypeError(f"{field_name} must be a float")
            if value <= 0.0:
                raise ValueError(f"{field_name} must be positive")
        object.__setattr__(
            self,
            "max_response_bytes",
            _validate_non_negative_int(self.max_response_bytes, "max_response_bytes"),
        )
        if self.max_response_bytes < 1:
            raise ValueError("max_response_bytes must be greater than zero")
        if self._client is not None and not isinstance(self._client, httpx.AsyncClient):
            raise TypeError("_client must be an httpx.AsyncClient or None")

    async def call_chat_json(
        self,
        *,
        request: ProviderRequest,
        bearer_key: str,
    ) -> ProviderResult:
        if type(bearer_key) is not str or not bearer_key.strip():
            raise OpenAICompatibleAdapterError("provider bearer key is missing")
        sanitized_key = bearer_key.strip()
        timeout = httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.read_timeout_seconds,
            write=self.write_timeout_seconds,
            pool=self.pool_timeout_seconds,
        )
        endpoint = urljoin(self.base_url, "chat/completions")
        max_tokens = min(
            max(request.max_output_characters // 4, _MIN_OUTPUT_TOKENS), _MAX_OUTPUT_TOKENS
        )
        payload = {
            "model": request.model_code,
            "messages": (
                {
                    "role": "system",
                    "content": "Return only strict JSON for the requested schema.",
                },
                {
                    "role": "user",
                    "content": request.prompt_text,
                },
            ),
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {sanitized_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        started = time.perf_counter()
        try:
            if self._client is None:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(endpoint, headers=headers, json=payload)
            else:
                response = await self._client.post(
                    endpoint, headers=headers, json=payload, timeout=timeout
                )
        except (httpx.HTTPError, ValueError) as error:
            raise OpenAICompatibleAdapterError("provider request failed") from error
        elapsed_ms = int((time.perf_counter() - started) * 1_000)

        if response.status_code < 200 or response.status_code >= 300:
            raise OpenAICompatibleAdapterError("provider returned non-success status")
        if len(response.content) > self.max_response_bytes:
            raise OpenAICompatibleAdapterError("provider response exceeded byte limit")

        try:
            parsed = json.loads(response.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OpenAICompatibleAdapterError("provider returned invalid json") from error

        if not isinstance(parsed, dict):
            raise OpenAICompatibleAdapterError("provider response must be a json object")
        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            raise OpenAICompatibleAdapterError("provider response choices are missing")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise OpenAICompatibleAdapterError("provider response choice is malformed")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise OpenAICompatibleAdapterError("provider response message is missing")
        content = message.get("content")
        if type(content) is not str or not content.strip():
            raise OpenAICompatibleAdapterError("provider response content is missing")
        normalized_output = content.strip()
        if len(normalized_output) > request.max_output_characters:
            raise OpenAICompatibleAdapterError("provider response exceeded character limit")

        usage = _extract_usage(parsed, latency_milliseconds=elapsed_ms)
        return ProviderResult(
            provider_code=request.provider_code,
            model_code=request.model_code,
            purpose=request.purpose,
            output_text=normalized_output,
            usage=usage,
            completed_at=datetime.now(tz=UTC),
        )
