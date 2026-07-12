"""Unit tests for deterministic knowledge chunking."""

from __future__ import annotations

import pytest
from closeros.application.knowledge_chunking import chunk_text_with_overlap


def test_chunking_returns_empty_tuple_for_blank_text() -> None:
    assert chunk_text_with_overlap(text="   ") == ()


def test_chunking_normalizes_newlines_and_strips_outer_whitespace() -> None:
    chunks = chunk_text_with_overlap(
        text="\r\n hello\r\nworld \r\n", max_characters=100, overlap_characters=10
    )
    assert len(chunks) == 1
    assert chunks[0].text == "hello\nworld"


def test_chunking_splits_long_text_with_overlap() -> None:
    text = " ".join(f"token{index}" for index in range(300))
    chunks = chunk_text_with_overlap(text=text, max_characters=120, overlap_characters=20)
    assert len(chunks) > 2
    for chunk in chunks:
        assert chunk.start_offset < chunk.end_offset
        assert chunk.text


def test_chunking_prefers_line_break_before_space_or_hard_stop() -> None:
    text = "alpha beta gamma\ndelta epsilon zeta"
    chunks = chunk_text_with_overlap(text=text, max_characters=17, overlap_characters=2)
    assert len(chunks) >= 2
    assert chunks[0].text.endswith("gamma")


def test_chunk_positions_increment_monotonically() -> None:
    text = " ".join("x" for _ in range(200))
    chunks = chunk_text_with_overlap(text=text, max_characters=50, overlap_characters=10)
    assert [chunk.position for chunk in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize(
    ("max_chars", "overlap"),
    [(0, 0), (10, -1), (10, 10), (10, 11)],
)
def test_chunking_rejects_invalid_limits(max_chars: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text_with_overlap(
            text="synthetic", max_characters=max_chars, overlap_characters=overlap
        )


def test_chunking_rejects_non_string_text() -> None:
    with pytest.raises(TypeError):
        chunk_text_with_overlap(text=123)  # type: ignore[arg-type]
