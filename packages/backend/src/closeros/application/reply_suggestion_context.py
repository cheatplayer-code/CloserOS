"""Bounded conversation context assembly for reply suggestions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from closeros.domain.reply_suggestion import ReplySuggestionError

# Keep the window small for LLM cost and grounding quality.
MAX_REPLY_CONTEXT_MESSAGES = 40
MAX_REPLY_CONTEXT_CHARS = 24_000
MAX_SUMMARY_ITEMS = 12


class ReplyContextTooLargeError(ReplySuggestionError):
    """Raised when even the latest customer turn cannot fit configured bounds."""


@dataclass(frozen=True, slots=True)
class ReplyContextAssembly:
    messages: tuple[tuple[UUID, str], ...]
    evidence_message_ids: tuple[UUID, ...]
    structured_summary: tuple[str, ...]
    used_summary: bool
    total_source_messages: int
    total_source_chars: int


def assemble_reply_context(
    messages: Sequence[tuple[UUID, str]],
    *,
    max_messages: int = MAX_REPLY_CONTEXT_MESSAGES,
    max_chars: int = MAX_REPLY_CONTEXT_CHARS,
) -> ReplyContextAssembly:
    """Assemble sanitized transcript for prompting.

    Rules:
    - Never silently drop the latest customer message.
    - Prefer recent verbatim sanitized turns.
    - When older history is omitted, emit a structured summary of omitted IDs/lengths.
    - If the latest message alone exceeds the char budget, fail closed.
    """
    if max_messages < 1 or max_chars < 1:
        raise ValueError("bounds must be positive")
    cleaned = [(message_id, text) for message_id, text in messages if text.strip()]
    total_chars = sum(len(text) for _message_id, text in cleaned)
    if not cleaned:
        return ReplyContextAssembly(
            messages=(),
            evidence_message_ids=(),
            structured_summary=(),
            used_summary=False,
            total_source_messages=0,
            total_source_chars=0,
        )

    latest_id, latest_text = cleaned[-1]
    if len(latest_text) > max_chars:
        raise ReplyContextTooLargeError("latest customer message exceeds context budget")

    selected: list[tuple[UUID, str]] = [(latest_id, latest_text)]
    used_chars = len(latest_text)
    for message_id, text in reversed(cleaned[:-1]):
        if len(selected) >= max_messages:
            break
        if used_chars + len(text) > max_chars:
            break
        selected.append((message_id, text))
        used_chars += len(text)
    selected.reverse()

    selected_ids = {message_id for message_id, _text in selected}
    omitted = [
        (message_id, text) for message_id, text in cleaned if message_id not in selected_ids
    ]
    summary: list[str] = []
    for message_id, text in omitted[:MAX_SUMMARY_ITEMS]:
        summary.append(f"omitted_message id={message_id} chars={len(text)}")
    if len(omitted) > MAX_SUMMARY_ITEMS:
        summary.append(f"omitted_additional_count={len(omitted) - MAX_SUMMARY_ITEMS}")

    return ReplyContextAssembly(
        messages=tuple(selected),
        evidence_message_ids=tuple(message_id for message_id, _text in selected),
        structured_summary=tuple(summary),
        used_summary=bool(summary),
        total_source_messages=len(cleaned),
        total_source_chars=total_chars,
    )
