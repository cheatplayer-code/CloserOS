"""Deterministic lexical term indexing for tenant-scoped knowledge retrieval."""

from __future__ import annotations

import hmac
import re
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from closeros.application.knowledge_search_key import KnowledgeSearchKeyProvider

_TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,64}")
_MAX_TERMS_PER_CHUNK = 64
_MAX_TERMS_PER_QUERY = 32

DEFAULT_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "with",
        "и",
        "в",
        "во",
        "на",
        "не",
        "что",
        "как",
        "по",
        "из",
        "за",
        "для",
    }
)


@dataclass(frozen=True, slots=True)
class IndexedKnowledgeTerm:
    term_digest: bytes
    weight_basis_points: int


def _normalize_text(text: str) -> str:
    return text.lower().replace("\r\n", "\n").replace("\r", "\n")


def extract_indexable_terms(
    *,
    text: str,
    stop_words: frozenset[str] = DEFAULT_STOP_WORDS,
    max_terms: int = _MAX_TERMS_PER_CHUNK,
) -> tuple[str, ...]:
    if type(text) is not str:
        raise TypeError("text must be a string")
    if type(max_terms) is not int or max_terms < 1:
        raise ValueError("max_terms must be a positive integer")

    tokens = [
        token for token in _TOKEN_PATTERN.findall(_normalize_text(text)) if token not in stop_words
    ]
    if not tokens:
        return ()
    counts = Counter(tokens)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(token for token, _ in ordered[:max_terms])


def _digest_term(*, key: bytes, term: str) -> bytes:
    return hmac.new(key, term.encode("utf-8"), sha256).digest()


def build_chunk_term_index(
    *,
    tenant_id: UUID,
    chunk_text: str,
    key_provider: KnowledgeSearchKeyProvider,
    stop_words: frozenset[str] = DEFAULT_STOP_WORDS,
    max_terms: int = _MAX_TERMS_PER_CHUNK,
) -> tuple[IndexedKnowledgeTerm, ...]:
    terms = extract_indexable_terms(text=chunk_text, stop_words=stop_words, max_terms=max_terms)
    if not terms:
        return ()
    key = key_provider.key_for_tenant(tenant_id=tenant_id)
    frequencies = Counter(
        token
        for token in _TOKEN_PATTERN.findall(_normalize_text(chunk_text))
        if token not in stop_words and token in set(terms)
    )
    max_frequency = max(frequencies.values()) if frequencies else 1
    indexed: list[IndexedKnowledgeTerm] = []
    for term in terms:
        frequency = frequencies.get(term, 1)
        weight = max(1, min(10_000, round((frequency / max_frequency) * 10_000)))
        indexed.append(
            IndexedKnowledgeTerm(
                term_digest=_digest_term(key=key, term=term),
                weight_basis_points=weight,
            )
        )
    return tuple(indexed)


def build_query_term_digests(
    *,
    tenant_id: UUID,
    query_text: str,
    key_provider: KnowledgeSearchKeyProvider,
    stop_words: frozenset[str] = DEFAULT_STOP_WORDS,
    max_terms: int = _MAX_TERMS_PER_QUERY,
) -> tuple[bytes, ...]:
    terms = extract_indexable_terms(text=query_text, stop_words=stop_words, max_terms=max_terms)
    if not terms:
        return ()
    key = key_provider.key_for_tenant(tenant_id=tenant_id)
    return tuple(_digest_term(key=key, term=term) for term in terms)
