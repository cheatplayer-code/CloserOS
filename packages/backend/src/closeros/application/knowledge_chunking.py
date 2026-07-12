"""Deterministic knowledge text chunking with configurable overlap."""

from __future__ import annotations

from dataclasses import dataclass

from closeros.domain.knowledge import CHUNK_MAX_CHARACTERS, CHUNK_OVERLAP_CHARACTERS


@dataclass(frozen=True, slots=True)
class KnowledgeChunkSlice:
    position: int
    start_offset: int
    end_offset: int
    text: str


def _normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _find_breakpoint(text: str, *, start: int, hard_stop: int) -> int:
    if hard_stop >= len(text):
        return len(text)
    boundary = text.rfind("\n", start, hard_stop + 1)
    if boundary <= start:
        boundary = text.rfind(" ", start, hard_stop + 1)
    if boundary <= start:
        return hard_stop
    return boundary


def chunk_text_with_overlap(
    *,
    text: str,
    max_characters: int = CHUNK_MAX_CHARACTERS,
    overlap_characters: int = CHUNK_OVERLAP_CHARACTERS,
) -> tuple[KnowledgeChunkSlice, ...]:
    if type(text) is not str:
        raise TypeError("text must be a string")
    if type(max_characters) is not int or max_characters < 1:
        raise ValueError("max_characters must be a positive integer")
    if type(overlap_characters) is not int or overlap_characters < 0:
        raise ValueError("overlap_characters must be a non-negative integer")
    if overlap_characters >= max_characters:
        raise ValueError("overlap_characters must be less than max_characters")

    normalized = _normalize_text(text)
    if not normalized:
        return ()

    chunks: list[KnowledgeChunkSlice] = []
    start = 0
    position = 0
    while start < len(normalized):
        hard_stop = min(len(normalized), start + max_characters)
        end = _find_breakpoint(normalized, start=start, hard_stop=hard_stop)
        if end <= start:
            end = hard_stop
        chunk_text = normalized[start:end].strip()
        if chunk_text:
            chunks.append(
                KnowledgeChunkSlice(
                    position=position,
                    start_offset=start,
                    end_offset=end,
                    text=chunk_text,
                )
            )
            position += 1
        if end >= len(normalized):
            break
        next_start = max(0, end - overlap_characters)
        if next_start <= start:
            next_start = end
        start = next_start

    return tuple(chunks)
