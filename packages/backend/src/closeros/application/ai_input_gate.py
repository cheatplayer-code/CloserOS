"""AI input gate that enforces policy, sanitization safety, limits, and digests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from uuid import UUID

from closeros.application.privacy_detector import detect_sensitive_data
from closeros.domain.ai_analysis import AiFailureCode, AiPurpose, TenantAiPolicy
from closeros.domain.privacy_redaction import AnalysisEligibility


class AiInputGateError(Exception):
    """Raised when sanitized AI input fails safety or policy checks."""

    def __init__(self, *, failure_code: AiFailureCode) -> None:
        self.failure_code = failure_code
        super().__init__("ai input gate rejected request")


def _sha256_digest(value: bytes) -> bytes:
    return hashlib.sha256(value).digest()


def _validate_non_empty_text(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class GateMessage:
    message_id: UUID
    sanitized_text: str = field(repr=False)
    eligibility: AnalysisEligibility = AnalysisEligibility.ELIGIBLE

    def __post_init__(self) -> None:
        if not isinstance(self.message_id, UUID):
            raise TypeError("message_id must be a UUID")
        object.__setattr__(
            self,
            "sanitized_text",
            _validate_non_empty_text(self.sanitized_text, "sanitized_text"),
        )
        if not isinstance(self.eligibility, AnalysisEligibility):
            raise TypeError("eligibility must be an AnalysisEligibility")


@dataclass(frozen=True, slots=True)
class AiGateAcceptedInput:
    purpose: AiPurpose
    messages: tuple[GateMessage, ...]
    input_text: str = field(repr=False)
    message_count: int
    total_characters: int
    input_digest: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, AiPurpose):
            raise TypeError("purpose must be an AiPurpose")
        if not isinstance(self.messages, tuple):
            raise TypeError("messages must be a tuple")
        if not self.messages:
            raise ValueError("messages must not be empty")
        if not all(isinstance(message, GateMessage) for message in self.messages):
            raise TypeError("messages must contain GateMessage values")
        object.__setattr__(
            self, "input_text", _validate_non_empty_text(self.input_text, "input_text")
        )
        if type(self.message_count) is not int:
            raise TypeError("message_count must be an int")
        if self.message_count != len(self.messages):
            raise ValueError("message_count must match messages length")
        if type(self.total_characters) is not int:
            raise TypeError("total_characters must be an int")
        if self.total_characters != len(self.input_text):
            raise ValueError("total_characters must match input_text length")
        if type(self.input_digest) is not bytes or len(self.input_digest) != 32:
            raise ValueError("input_digest must contain exactly 32 bytes")


class AiInputGate:
    def verify_and_hash(
        self,
        *,
        tenant_id: UUID,
        policy: TenantAiPolicy,
        purpose: AiPurpose,
        messages: tuple[GateMessage, ...],
    ) -> AiGateAcceptedInput:
        if not isinstance(tenant_id, UUID):
            raise TypeError("tenant_id must be a UUID")
        if not isinstance(policy, TenantAiPolicy):
            raise TypeError("policy must be a TenantAiPolicy")
        if policy.tenant_id != tenant_id:
            raise AiInputGateError(failure_code=AiFailureCode.PURPOSE_NOT_ALLOWED)
        if not policy.enabled:
            raise AiInputGateError(failure_code=AiFailureCode.POLICY_DISABLED)
        if purpose not in policy.allowed_purposes:
            raise AiInputGateError(failure_code=AiFailureCode.PURPOSE_NOT_ALLOWED)
        if not messages:
            raise AiInputGateError(failure_code=AiFailureCode.SANITIZATION_MISSING)
        if len(messages) > policy.maximum_messages_per_request:
            raise AiInputGateError(failure_code=AiFailureCode.INPUT_TOO_LARGE)

        normalized_messages: list[GateMessage] = []
        for message in messages:
            if message.eligibility is not AnalysisEligibility.ELIGIBLE:
                raise AiInputGateError(failure_code=AiFailureCode.SANITIZATION_BLOCKED)
            summary = detect_sensitive_data(message.sanitized_text)
            if summary.total_count > 0:
                raise AiInputGateError(failure_code=AiFailureCode.SANITIZATION_BLOCKED)
            normalized_messages.append(message)

        serialized_lines = [
            f"{index + 1}. {message.message_id}: {message.sanitized_text}"
            for index, message in enumerate(normalized_messages)
        ]
        input_text = "\n".join(serialized_lines)
        total_characters = len(input_text)
        if total_characters > policy.maximum_sanitized_characters:
            raise AiInputGateError(failure_code=AiFailureCode.INPUT_TOO_LARGE)
        digest = _sha256_digest(input_text.encode("utf-8"))
        return AiGateAcceptedInput(
            purpose=purpose,
            messages=tuple(normalized_messages),
            input_text=input_text,
            message_count=len(normalized_messages),
            total_characters=total_characters,
            input_digest=digest,
        )
