"""Unit tests for lexical knowledge term indexing and query digests."""

from __future__ import annotations

from uuid import UUID

import pytest
from closeros.application.knowledge_search_key import DevKnowledgeSearchKeyProvider
from closeros.application.knowledge_term_index import (
    build_chunk_term_index,
    build_query_term_digests,
    extract_indexable_terms,
)

TENANT_A = UUID("00000000-0000-0000-0000-000000000001")
TENANT_B = UUID("00000000-0000-0000-0000-000000000002")


def test_extract_indexable_terms_indexes_russian_and_kazakh() -> None:
    russian = extract_indexable_terms(text="Клиент спрашивает цену дивана в Алматы")
    kazakh = extract_indexable_terms(text="Қонақ диван бағасын сұрады Алматыда")
    assert "клиент" in russian
    assert "дивана" in russian or "диван" in russian
    assert "қонақ" in kazakh
    assert "диван" in kazakh
    assert "бағасын" in kazakh


def test_extract_indexable_terms_keeps_mixed_language_product_phrase() -> None:
    terms = extract_indexable_terms(text="Sofa модель X100 серый өңдіріс")
    assert "sofa" in terms
    assert "модель" in terms
    assert "x100" in terms
    assert "серый" in terms
    assert "өңдіріс" in terms


def test_extract_indexable_terms_drops_english_and_russian_stop_words() -> None:
    terms = extract_indexable_terms(text="The и в во на цена для клиента")
    assert "the" not in terms
    assert "и" not in terms
    assert "для" not in terms
    assert "цена" in terms
    assert "клиента" in terms


def test_build_chunk_term_index_digests_omit_plaintext_tokens() -> None:
    provider = DevKnowledgeSearchKeyProvider()
    indexed = build_chunk_term_index(
        tenant_id=TENANT_A,
        chunk_text="скрытый токен price",
        key_provider=provider,
    )
    serialized = b"".join(item.term_digest for item in indexed)
    assert b"price" not in serialized
    assert "токен".encode() not in serialized


def test_term_index_version_is_explicit() -> None:
    from closeros.application.knowledge_term_index import TERM_INDEX_VERSION

    assert TERM_INDEX_VERSION.startswith("v1-unicode")


def test_extract_indexable_terms_orders_by_frequency_then_token() -> None:
    terms = extract_indexable_terms(text="alpha beta alpha gamma beta alpha", max_terms=3)
    assert terms == ("alpha", "beta", "gamma")


def test_extract_indexable_terms_returns_empty_when_no_tokens() -> None:
    assert extract_indexable_terms(text="--- !! ??") == ()


@pytest.mark.parametrize("max_terms", [0, -1])
def test_extract_indexable_terms_rejects_non_positive_max_terms(max_terms: int) -> None:
    with pytest.raises(ValueError):
        extract_indexable_terms(text="alpha beta", max_terms=max_terms)


def test_build_chunk_term_index_returns_weighted_digests() -> None:
    provider = DevKnowledgeSearchKeyProvider()
    indexed = build_chunk_term_index(
        tenant_id=TENANT_A,
        chunk_text="alpha alpha alpha beta beta gamma",
        key_provider=provider,
    )
    assert indexed
    assert all(len(item.term_digest) == 32 for item in indexed)
    assert indexed[0].weight_basis_points >= indexed[-1].weight_basis_points


def test_build_chunk_term_index_returns_empty_for_non_indexable_chunk() -> None:
    provider = DevKnowledgeSearchKeyProvider()
    assert build_chunk_term_index(tenant_id=TENANT_A, chunk_text="---", key_provider=provider) == ()


def test_query_term_digests_are_deterministic_per_tenant() -> None:
    provider = DevKnowledgeSearchKeyProvider()
    a = build_query_term_digests(
        tenant_id=TENANT_A,
        query_text="pricing discount timeline",
        key_provider=provider,
    )
    b = build_query_term_digests(
        tenant_id=TENANT_A,
        query_text="pricing discount timeline",
        key_provider=provider,
    )
    assert a == b


def test_query_term_digests_change_with_tenant_when_provider_is_tenant_aware() -> None:
    class TenantAwareProvider:
        search_key_version = "test-v1"

        def key_for_tenant(self, *, tenant_id: UUID) -> bytes:
            return tenant_id.bytes + tenant_id.bytes

    provider = TenantAwareProvider()
    a = build_query_term_digests(
        tenant_id=TENANT_A,
        query_text="price timeline",
        key_provider=provider,
    )
    b = build_query_term_digests(
        tenant_id=TENANT_B,
        query_text="price timeline",
        key_provider=provider,
    )
    assert a != b


def test_query_term_digests_returns_empty_for_blank_query() -> None:
    provider = DevKnowledgeSearchKeyProvider()
    assert (
        build_query_term_digests(tenant_id=TENANT_A, query_text="  ", key_provider=provider) == ()
    )
