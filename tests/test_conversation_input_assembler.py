"""Unit tests for deterministic conversation input assembly."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from closeros.application.conversation_input_assembler import (
    ConversationInputAssembler,
    SanitizedConversationMessage,
)
from closeros.domain.ai_analysis import AiPurpose


def _ts(hour: int, minute: int) -> datetime:
    return datetime(2026, 7, 12, hour, minute, tzinfo=UTC)


def _msg(
    message_id: str, sender: str, hour: int, minute: int, text: str
) -> SanitizedConversationMessage:
    return SanitizedConversationMessage(
        message_id=UUID(message_id),
        sender_role=sender,
        sent_at=_ts(hour, minute),
        sanitized_text=text,
    )


def test_assemble_orders_by_timestamp_then_id() -> None:
    assembler = ConversationInputAssembler()
    first = _msg("00000000-0000-0000-0000-000000000003", "manager", 10, 5, "B")
    second = _msg("00000000-0000-0000-0000-000000000001", "customer", 10, 0, "A")
    assembled = assembler.assemble_for_thread(
        purpose=AiPurpose.CONVERSATION_ANALYSIS,
        messages=(first, second),
    )
    assert assembled.ordered_messages[0].message_id == second.message_id
    assert assembled.ordered_messages[1].message_id == first.message_id


def test_assemble_breaks_same_timestamp_ties_by_uuid_string() -> None:
    assembler = ConversationInputAssembler()
    m1 = _msg("00000000-0000-0000-0000-000000000010", "manager", 10, 0, "Later id")
    m2 = _msg("00000000-0000-0000-0000-000000000009", "manager", 10, 0, "Earlier id")
    assembled = assembler.assemble_for_thread(
        purpose=AiPurpose.CONVERSATION_ANALYSIS,
        messages=(m1, m2),
    )
    assert assembled.ordered_messages[0].message_id == m2.message_id


def test_assemble_renders_transcript_lines_with_sender_and_timestamp() -> None:
    assembler = ConversationInputAssembler()
    assembled = assembler.assemble_for_thread(
        purpose=AiPurpose.CONVERSATION_ANALYSIS,
        messages=(_msg("00000000-0000-0000-0000-000000000001", "customer", 10, 1, "Need pricing"),),
    )
    assert "[2026-07-12T10:01:00+00:00] customer: Need pricing" in assembled.rendered_transcript


def test_assemble_produces_deterministic_digest_for_same_input() -> None:
    assembler = ConversationInputAssembler()
    messages = (
        _msg("00000000-0000-0000-0000-000000000001", "customer", 10, 1, "Need pricing"),
        _msg("00000000-0000-0000-0000-000000000002", "manager", 10, 2, "Sure"),
    )
    a = assembler.assemble_for_thread(purpose=AiPurpose.CONVERSATION_ANALYSIS, messages=messages)
    b = assembler.assemble_for_thread(purpose=AiPurpose.CONVERSATION_ANALYSIS, messages=messages)
    assert a.transcript_digest == b.transcript_digest


def test_assemble_rejects_empty_message_list() -> None:
    assembler = ConversationInputAssembler()
    with pytest.raises(ValueError, match="must not be empty"):
        assembler.assemble_for_thread(
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            messages=(),
        )


def test_assemble_rejects_non_tuple_messages() -> None:
    assembler = ConversationInputAssembler()
    with pytest.raises(TypeError, match="tuple"):
        assembler.assemble_for_thread(
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            messages=[  # type: ignore[arg-type]
                _msg("00000000-0000-0000-0000-000000000001", "customer", 10, 1, "x")
            ],
        )
