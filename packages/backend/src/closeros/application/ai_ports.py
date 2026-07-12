"""Application ports and value objects for provider-neutral AI gateway calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.domain.ai_analysis import AiProviderCode, AiPurpose, AiUsage

_MAX_PROVIDER_CODE_LENGTH = 64


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _validate_non_empty_text(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _validate_non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _validate_digest(value: object, field_name: str) -> bytes:
    if type(value) is not bytes:
        raise TypeError(f"{field_name} must be bytes")
    if len(value) != 32:
        raise ValueError(f"{field_name} must contain exactly 32 bytes")
    return value


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    tenant_id: UUID
    provider_code: AiProviderCode
    purpose: AiPurpose
    model_code: str
    prompt_version: str
    rubric_version: str
    prompt_text: str = field(repr=False)
    evidence_message_ids: tuple[UUID, ...] = ()
    max_output_characters: int = 32_768
    input_digest: bytes = field(repr=False, default=b"")
    requested_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise TypeError("tenant_id must be a UUID")
        if not isinstance(self.provider_code, AiProviderCode):
            raise TypeError("provider_code must be an AiProviderCode")
        if not isinstance(self.purpose, AiPurpose):
            raise TypeError("purpose must be an AiPurpose")
        object.__setattr__(
            self, "model_code", _validate_non_empty_text(self.model_code, "model_code")
        )
        if len(self.model_code) > _MAX_PROVIDER_CODE_LENGTH:
            raise ValueError(f"model_code must not exceed {_MAX_PROVIDER_CODE_LENGTH} characters")
        object.__setattr__(
            self,
            "prompt_version",
            _validate_non_empty_text(self.prompt_version, "prompt_version"),
        )
        object.__setattr__(
            self,
            "rubric_version",
            _validate_non_empty_text(self.rubric_version, "rubric_version"),
        )
        object.__setattr__(
            self, "prompt_text", _validate_non_empty_text(self.prompt_text, "prompt_text")
        )
        if not isinstance(self.evidence_message_ids, tuple):
            raise TypeError("evidence_message_ids must be a tuple")
        if not all(isinstance(message_id, UUID) for message_id in self.evidence_message_ids):
            raise TypeError("evidence_message_ids must contain UUID values")
        object.__setattr__(
            self,
            "max_output_characters",
            _validate_non_negative_int(self.max_output_characters, "max_output_characters"),
        )
        if self.max_output_characters < 1:
            raise ValueError("max_output_characters must be greater than zero")
        if self.input_digest:
            object.__setattr__(
                self, "input_digest", _validate_digest(self.input_digest, "input_digest")
            )
        if self.requested_at is not None:
            object.__setattr__(
                self,
                "requested_at",
                _validate_timezone_aware_datetime(self.requested_at, "requested_at"),
            )


@dataclass(frozen=True, slots=True)
class ProviderResult:
    provider_code: AiProviderCode
    model_code: str
    purpose: AiPurpose
    output_text: str = field(repr=False)
    output_digest: bytes = field(repr=False, default=b"")
    usage: AiUsage | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_code, AiProviderCode):
            raise TypeError("provider_code must be an AiProviderCode")
        object.__setattr__(
            self, "model_code", _validate_non_empty_text(self.model_code, "model_code")
        )
        if len(self.model_code) > _MAX_PROVIDER_CODE_LENGTH:
            raise ValueError(f"model_code must not exceed {_MAX_PROVIDER_CODE_LENGTH} characters")
        if not isinstance(self.purpose, AiPurpose):
            raise TypeError("purpose must be an AiPurpose")
        object.__setattr__(
            self, "output_text", _validate_non_empty_text(self.output_text, "output_text")
        )
        if self.output_digest:
            object.__setattr__(
                self, "output_digest", _validate_digest(self.output_digest, "output_digest")
            )
        if self.usage is not None and not isinstance(self.usage, AiUsage):
            raise TypeError("usage must be an AiUsage or None")
        if self.completed_at is not None:
            object.__setattr__(
                self,
                "completed_at",
                _validate_timezone_aware_datetime(self.completed_at, "completed_at"),
            )


class AiProvider(Protocol):
    @property
    def provider_code(self) -> AiProviderCode: ...

    async def call_chat_json(
        self,
        *,
        request: ProviderRequest,
        bearer_key: str,
    ) -> ProviderResult: ...


class AiProviderRegistry(Protocol):
    def get_provider(self, *, provider_code: AiProviderCode) -> AiProvider: ...


class AiCredentialResolver(Protocol):
    async def resolve_bearer_key(
        self,
        *,
        tenant_id: UUID,
        provider_code: AiProviderCode,
    ) -> str | None: ...


class AiClock(Protocol):
    def now(self) -> datetime: ...
