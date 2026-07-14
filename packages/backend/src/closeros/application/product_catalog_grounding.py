"""Deterministic catalog grounding / hallucination resistance."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.domain.product_catalog import (
    CatalogDomainError,
    CatalogGroundingError,
    CatalogSearchHit,
    CommercialActionCode,
    CommercialPolicy,
    FactVerificationStatus,
    Product,
    is_customer_visible_status,
)

SAFE_STALE_RESPONSE = "I need to confirm the current price or availability before promising it."


@dataclass(frozen=True, slots=True)
class AiCatalogClaim:
    """Model-emitted claim. Critical facts must match backend-loaded values."""

    product_id: UUID
    variant_id: UUID
    claimed_amount_minor: int | None = None
    claimed_currency: str | None = None
    claimed_in_stock: bool | None = None
    claimed_discount_basis_points: int | None = None
    commercial_action: CommercialActionCode | None = None
    reply_text: str | None = None
    product_name_in_text: str | None = None


@dataclass(frozen=True, slots=True)
class GroundingResult:
    accepted: bool
    reason_code: str | None
    safe_fallback_text: str | None
    rendered_price_fragment: str | None
    rendered_stock_fragment: str | None


def validate_catalog_claim(
    *,
    tenant_id: UUID,
    claim: AiCatalogClaim,
    product: Product | None,
    hit: CatalogSearchHit | None,
    tool_hits: Sequence[CatalogSearchHit],
    policy: CommercialPolicy | None,
    now: datetime,
) -> GroundingResult:
    del now  # freshness already applied when building hits
    if product is None or hit is None:
        return GroundingResult(
            accepted=False,
            reason_code="unknown_product",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )
    if product.tenant_id != tenant_id or hit.product_id != product.id:
        return GroundingResult(
            accepted=False,
            reason_code="cross_tenant_product",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )
    if not is_customer_visible_status(product.status):
        return GroundingResult(
            accepted=False,
            reason_code="inactive_product",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )
    if hit.variant_id != claim.variant_id:
        return GroundingResult(
            accepted=False,
            reason_code="variant_mismatch",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )
    if not any(
        item.product_id == claim.product_id and item.variant_id == claim.variant_id
        for item in tool_hits
    ):
        return GroundingResult(
            accepted=False,
            reason_code="product_omitted_from_tool_results",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )
    if not hit.price_provenance.usable or not hit.inventory_provenance.usable:
        return GroundingResult(
            accepted=False,
            reason_code="stale_or_unusable_fact",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )
    if claim.claimed_amount_minor is not None and claim.claimed_amount_minor != hit.amount_minor:
        return GroundingResult(
            accepted=False,
            reason_code="price_mismatch",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )
    if claim.claimed_currency is not None and claim.claimed_currency.upper() != hit.currency:
        return GroundingResult(
            accepted=False,
            reason_code="currency_mismatch",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )
    if claim.claimed_in_stock is not None and claim.claimed_in_stock != hit.in_stock:
        return GroundingResult(
            accepted=False,
            reason_code="stock_mismatch",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )
    if claim.claimed_discount_basis_points is not None and (
        policy is None or not policy.allow_discount
    ):
        return GroundingResult(
            accepted=False,
            reason_code="discount_not_permitted",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )
    if (
        claim.claimed_discount_basis_points is not None
        and policy is not None
        and claim.claimed_discount_basis_points > policy.max_discount_basis_points
    ):
        return GroundingResult(
            accepted=False,
            reason_code="discount_exceeds_policy",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )
    if claim.commercial_action is CommercialActionCode.OFFER_DISCOUNT and (
        policy is None or not policy.allow_discount
    ):
        return GroundingResult(
            accepted=False,
            reason_code="discount_action_blocked",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )
    if claim.reply_text:
        lowered = claim.reply_text.casefold()
        if "ignore catalog" in lowered or "ignore the catalog" in lowered:
            return GroundingResult(
                accepted=False,
                reason_code="prompt_injection",
                safe_fallback_text=SAFE_STALE_RESPONSE,
                rendered_price_fragment=None,
                rendered_stock_fragment=None,
            )
    if (
        claim.product_name_in_text
        and claim.product_name_in_text.strip()
        and claim.product_name_in_text.strip().casefold() != product.name.casefold()
    ):
        return GroundingResult(
            accepted=False,
            reason_code="product_name_mismatch",
            safe_fallback_text=SAFE_STALE_RESPONSE,
            rendered_price_fragment=None,
            rendered_stock_fragment=None,
        )

    price_fragment = f"{hit.amount_minor} {hit.currency}"
    stock_fragment = "in_stock" if hit.in_stock else "out_of_stock"
    return GroundingResult(
        accepted=True,
        reason_code=None,
        safe_fallback_text=None,
        rendered_price_fragment=price_fragment,
        rendered_stock_fragment=stock_fragment,
    )


def require_grounded_or_raise(result: GroundingResult) -> GroundingResult:
    if not result.accepted:
        raise CatalogGroundingError(result.reason_code or "grounding_failed")
    return result


def assert_fact_status_customer_safe(status: FactVerificationStatus) -> None:
    if status in {FactVerificationStatus.STALE, FactVerificationStatus.UNVERIFIED}:
        raise CatalogDomainError("fact cannot be stated to customer")
