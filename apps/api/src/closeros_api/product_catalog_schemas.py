"""HTTP schemas for product catalog API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CatalogProductCreateRequest(BaseModel):
    sku: str
    name: str
    category_code: str
    description: str = ""


class CatalogProductUpdateRequest(BaseModel):
    expected_version: int
    name: str | None = None
    category_code: str | None = None
    description: str | None = None


class CatalogPublishRequest(BaseModel):
    expected_version: int


class CatalogStatusChangeRequest(BaseModel):
    expected_version: int
    status: str


class CatalogVariantCreateRequest(BaseModel):
    sku: str
    display_name: str
    attributes: dict[str, str] = Field(default_factory=dict)


class CatalogPriceSetRequest(BaseModel):
    amount_minor: int
    currency: str
    price_kind: str = "list"
    verification_status: str = "verified"


class CatalogInventorySetRequest(BaseModel):
    location_code: str
    available_quantity: int
    reserved_quantity: int = 0
    verification_status: str = "live"


class CatalogProductResponse(BaseModel):
    id: UUID
    sku: str
    name: str
    category_code: str
    description: str
    status: str
    version: int
    updated_at: datetime


class CatalogVariantResponse(BaseModel):
    id: UUID
    product_id: UUID
    sku: str
    display_name: str
    attributes: dict[str, str]
    status: str
    version: int


class CatalogProductDetailResponse(BaseModel):
    product: CatalogProductResponse
    variants: list[CatalogVariantResponse]


class CatalogProductListResponse(BaseModel):
    items: list[CatalogProductResponse]


class CatalogSearchHitResponse(BaseModel):
    product_id: UUID
    variant_id: UUID
    product_sku: str
    variant_sku: str
    product_name: str
    variant_display_name: str
    category_code: str
    amount_minor: int
    currency: str
    available_quantity: int
    in_stock: bool
    price_usable: bool
    inventory_usable: bool
    delivery_usable: bool
    attributes: dict[str, str]


class CatalogSearchResponse(BaseModel):
    items: list[CatalogSearchHitResponse]


class CatalogImportUploadRequest(BaseModel):
    csv_text: str
    delimiter: str = ","
    mapping: dict[str, str]
    dry_run: bool = False


class CatalogImportRunResponse(BaseModel):
    id: UUID | None = None
    status: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    dry_run: bool = False
    rows: list[dict[str, Any]] | None = None


class CatalogToolExecuteRequest(BaseModel):
    tool: str
    arguments: dict[str, Any]


class CatalogToolExecuteResponse(BaseModel):
    tool: str
    results: list[dict[str, Any]]
    warnings: list[str]


class CatalogGroundClaimRequest(BaseModel):
    product_id: UUID
    variant_id: UUID
    claimed_amount_minor: int | None = None
    claimed_currency: str | None = None
    claimed_in_stock: bool | None = None
    claimed_discount_basis_points: int | None = None
    commercial_action: str | None = None
    reply_text: str | None = None
    product_name_in_text: str | None = None
    tool_result_product_ids: list[UUID] = Field(default_factory=list)


class CatalogGroundClaimResponse(BaseModel):
    accepted: bool
    reason_code: str | None
    safe_fallback_text: str | None
    rendered_price_fragment: str | None
    rendered_stock_fragment: str | None
