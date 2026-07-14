"""Post-validation grounding enrichment for reply candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from closeros.domain.product_catalog import CatalogSearchHit


def enrich_candidate_warnings_from_catalog(
    candidate: Mapping[str, Any],
    *,
    product_hits: Sequence[CatalogSearchHit],
) -> dict[str, Any]:
    """Attach deterministic grounding warnings; never invent catalog facts."""
    hit_by_key = {(hit.product_id, hit.variant_id): hit for hit in product_hits}
    warnings = list(candidate.get("warnings", []))
    for ref in candidate.get("product_references", []):
        try:
            key = (UUID(str(ref["product_id"])), UUID(str(ref["variant_id"])))
        except (KeyError, TypeError, ValueError):
            continue
        hit = hit_by_key.get(key)
        if hit is None:
            continue
        if not hit.inventory_provenance.usable:
            warning = "stale_stock"
            if warning not in warnings:
                warnings.append(warning)
        if not hit.price_provenance.usable:
            warning = "stale_price"
            if warning not in warnings:
                warnings.append(warning)
    updated = dict(candidate)
    updated["warnings"] = warnings
    return updated


def enrich_validated_candidates(
    *,
    recommended: Mapping[str, Any],
    alternatives: Sequence[Mapping[str, Any]],
    product_hits: Sequence[CatalogSearchHit],
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    return (
        enrich_candidate_warnings_from_catalog(recommended, product_hits=product_hits),
        tuple(
            enrich_candidate_warnings_from_catalog(item, product_hits=product_hits)
            for item in alternatives
        ),
    )
