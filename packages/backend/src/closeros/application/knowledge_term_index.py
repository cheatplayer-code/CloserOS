"""Deterministic lexical term indexing for tenant-scoped knowledge retrieval."""

from __future__ import annotations

import hmac
import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from closeros.application.knowledge_search_key import KnowledgeSearchKeyProvider

# Bumped when tokenization/digest semantics change. Reindex required.
TERM_INDEX_VERSION = "v1-unicode-term-v1"

_MAX_TERMS_PER_CHUNK = 64
_MAX_TERMS_PER_QUERY = 32
_MIN_TOKEN_LENGTH = 2
_MAX_TOKEN_LENGTH = 64

DEFAULT_STOP_WORDS: frozenset[str] = frozenset(
    {
        # English
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
        # Russian
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
        "а",
        "но",
        "или",
        "же",
        "к",
        "о",
        "об",
        "от",
        "со",
        "то",
        "это",
        "этот",
        "эта",
        "эти",
        "он",
        "она",
        "они",
        "мы",
        "вы",
        "их",
        "его",
        "ее",
        "если",
        "когда",
        "чтобы",
        "также",
        "уже",
        "есть",
        "будет",
        "были",
        "был",
        "была",
        # Kazakh
        "және",
        "мен",
        "бен",
        "пен",
        "де",
        "да",
        "те",
        "та",
        "үшін",
        "немесе",
        "бірақ",
        "емес",
        "жоқ",
        "иә",
        "бұл",
        "сол",
        "осы",
        "анау",
        "мынау",
        "ол",
        "олар",
        "біз",
        "сен",
        "сіздер",
        "бар",
        "керек",
        "қажет",
        "сияқты",
        "туралы",
        "арқылы",
        "кейін",
        "бұрын",
        "өте",
        "ғана",
        "тек",
        "ең",
    }
)


@dataclass(frozen=True, slots=True)
class IndexedKnowledgeTerm:
    term_digest: bytes
    weight_basis_points: int


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    folded = normalized.casefold()
    return " ".join(folded.split())


def _is_token_char(char: str) -> bool:
    return char.isalpha() or char.isdecimal()


def _iter_raw_tokens(normalized_text: str) -> Iterator[str]:
    buffer: list[str] = []
    for char in normalized_text:
        if _is_token_char(char):
            buffer.append(char)
            continue
        if buffer:
            yield "".join(buffer)
            buffer.clear()
    if buffer:
        yield "".join(buffer)


def _all_indexable_token_stream(
    *,
    text: str,
    stop_words: frozenset[str],
) -> list[str]:
    tokens: list[str] = []
    for raw in _iter_raw_tokens(_normalize_text(text)):
        if len(raw) < _MIN_TOKEN_LENGTH or len(raw) > _MAX_TOKEN_LENGTH:
            continue
        if raw in stop_words:
            continue
        tokens.append(raw)
    return tokens


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

    tokens = _all_indexable_token_stream(text=text, stop_words=stop_words)
    if not tokens:
        return ()
    counts = Counter(tokens)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(token for token, _ in ordered[:max_terms])


def _digest_term(*, key: bytes, term: str) -> bytes:
    payload = f"{TERM_INDEX_VERSION}:{term}".encode()
    return hmac.new(key, payload, sha256).digest()


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
    term_set = set(terms)
    frequencies = Counter(
        token
        for token in _all_indexable_token_stream(text=chunk_text, stop_words=stop_words)
        if token in term_set
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


__all__ = [
    "DEFAULT_STOP_WORDS",
    "TERM_INDEX_VERSION",
    "IndexedKnowledgeTerm",
    "build_chunk_term_index",
    "build_query_term_digests",
    "extract_indexable_terms",
]
