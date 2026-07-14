"""AI tool execution for catalog search — tenant context from auth, never from the model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from closeros.application.audit_recording import AuditContext
from closeros.application.product_catalog_service import ProductCatalogService
from closeros.application.tenant_context import TenantContext
from closeros.domain.product_catalog import (
    MAX_SEARCH_RESULTS,
    CatalogDomainError,
    CatalogSearchFilters,
    CatalogSearchHit,
)


@dataclass(frozen=True, slots=True)
class CatalogToolRequest:
    tool: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CatalogToolResponse:
    tool: str
    results: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]


def _hit_to_dict(hit: CatalogSearchHit) -> dict[str, Any]:
    return {
        "product_id": str(hit.product_id),
        "variant_id": str(hit.variant_id),
        "product_sku": hit.product_sku,
        "variant_sku": hit.variant_sku,
        "product_name": hit.product_name,
        "variant_display_name": hit.variant_display_name,
        "category_code": hit.category_code,
        "amount_minor": hit.amount_minor,
        "currency": hit.currency,
        "available_quantity": hit.available_quantity,
        "in_stock": hit.in_stock,
        "attributes": dict(hit.attributes),
        "price_usable": hit.price_provenance.usable,
        "inventory_usable": hit.inventory_provenance.usable,
        "delivery_status": hit.delivery_status.value if hit.delivery_status else None,
        "delivery_usable": hit.delivery_usable,
        "price_verification_status": hit.price_provenance.verification_status.value,
        "inventory_verification_status": hit.inventory_provenance.verification_status.value,
    }


class CatalogToolExecutor:
    """Executes model-requested catalog tools with application-owned authorization."""

    def __init__(self, catalog_service: ProductCatalogService) -> None:
        self._catalog = catalog_service

    async def execute(
        self,
        *,
        context: TenantContext,
        request: CatalogToolRequest,
        audit_context: AuditContext,
    ) -> CatalogToolResponse:
        if request.tool != "search_products":
            raise CatalogDomainError("unsupported catalog tool")

        args = dict(request.arguments)
        if "tenant_id" in args:
            raise CatalogDomainError("tenant_id must not be supplied by the model")

        limit = int(args.get("limit", 10))
        if limit < 1 or limit > MAX_SEARCH_RESULTS:
            raise CatalogDomainError("limit out of bounds")

        filters = CatalogSearchFilters(
            category=args.get("category"),
            budget_min_minor=args.get("budget_min_minor"),
            budget_max_minor=args.get("budget_max_minor"),
            currency=args.get("currency"),
            color=args.get("color"),
            material=args.get("material"),
            dimensions=args.get("dimensions"),
            location=args.get("location"),
            in_stock_only=bool(args.get("in_stock_only", False)),
            query_text=args.get("query_text"),
            limit=limit,
        )
        hits = await self._catalog.search_products(
            context=context, filters=filters, audit_context=audit_context
        )
        warnings: list[str] = []
        for hit in hits:
            if not hit.price_provenance.usable or not hit.inventory_provenance.usable:
                warnings.append("stale_or_unusable_fact")
        return CatalogToolResponse(
            tool="search_products",
            results=tuple(_hit_to_dict(hit) for hit in hits),
            warnings=tuple(sorted(set(warnings))),
        )


def parse_tool_request(payload: Mapping[str, Any]) -> CatalogToolRequest:
    tool = payload.get("tool")
    arguments = payload.get("arguments")
    if type(tool) is not str or not tool:
        raise CatalogDomainError("tool must be a non-empty string")
    if not isinstance(arguments, Mapping):
        raise CatalogDomainError("arguments must be an object")
    # Reject nested tenant identifiers aggressively
    for key in arguments:
        if str(key).casefold() in {"tenant_id", "tenantid", "tenant"}:
            raise CatalogDomainError("tenant_id must not be supplied by the model")
    return CatalogToolRequest(tool=tool, arguments=arguments)
