"""Deterministic sanitized conversation assembly for AI analysis input."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from closeros.application.ai_input_gate import GateMessage
from closeros.domain.ai_analysis import AiPurpose


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


@dataclass(frozen=True, slots=True)
class SanitizedConversationMessage:
    message_id: UUID
    sender_role: str
    sent_at: datetime
    sanitized_text: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.message_id, UUID):
            raise TypeError("message_id must be a UUID")
        object.__setattr__(
            self, "sender_role", _validate_non_empty_text(self.sender_role, "sender_role")
        )
        object.__setattr__(
            self, "sent_at", _validate_timezone_aware_datetime(self.sent_at, "sent_at")
        )
        object.__setattr__(
            self,
            "sanitized_text",
            _validate_non_empty_text(self.sanitized_text, "sanitized_text"),
        )


@dataclass(frozen=True, slots=True)
class AssembledConversationInput:
    purpose: AiPurpose
    ordered_messages: tuple[GateMessage, ...]
    rendered_transcript: str = field(repr=False)
    transcript_digest: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, AiPurpose):
            raise TypeError("purpose must be an AiPurpose")
        if not isinstance(self.ordered_messages, tuple):
            raise TypeError("ordered_messages must be a tuple")
        if not all(isinstance(message, GateMessage) for message in self.ordered_messages):
            raise TypeError("ordered_messages must contain GateMessage values")
        object.__setattr__(
            self,
            "rendered_transcript",
            _validate_non_empty_text(self.rendered_transcript, "rendered_transcript"),
        )
        if type(self.transcript_digest) is not bytes or len(self.transcript_digest) != 32:
            raise ValueError("transcript_digest must contain exactly 32 bytes")


class ConversationInputAssembler:
    def assemble_for_thread(
        self,
        *,
        purpose: AiPurpose,
        messages: tuple[SanitizedConversationMessage, ...],
    ) -> AssembledConversationInput:
        if not isinstance(purpose, AiPurpose):
            raise TypeError("purpose must be an AiPurpose")
        if not isinstance(messages, tuple):
            raise TypeError("messages must be a tuple")
        if not messages:
            raise ValueError("messages must not be empty")
        if not all(isinstance(message, SanitizedConversationMessage) for message in messages):
            raise TypeError("messages must contain SanitizedConversationMessage values")

        ordered = tuple(
            sorted(
                messages,
                key=lambda item: (
                    item.sent_at,
                    str(item.message_id),
                ),
            )
        )
        gate_messages = tuple(
            GateMessage(message_id=item.message_id, sanitized_text=item.sanitized_text)
            for item in ordered
        )
        transcript_lines = [
            f"[{item.sent_at.isoformat()}] {item.sender_role}: {item.sanitized_text}"
            for item in ordered
        ]
        transcript = "\n".join(transcript_lines)
        digest = hashlib.sha256(transcript.encode("utf-8")).digest()
        return AssembledConversationInput(
            purpose=purpose,
            ordered_messages=gate_messages,
            rendered_transcript=transcript,
            transcript_digest=digest,
        )
