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


def test_extract_indexable_terms_drops_stop_words_and_lowercases() -> None:
    terms = extract_indexable_terms(text="The customer asks for PRICE and discount in Алматы")
    assert "the" not in terms
    assert "for" not in terms
    assert "price" in terms


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
