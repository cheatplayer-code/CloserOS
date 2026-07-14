"""Persistence ports for the product catalog bounded context."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from closeros.domain.product_catalog import (
    CatalogFreshnessPolicy,
    CatalogImportRowResult,
    CatalogImportRun,
    CatalogSearchFilters,
    CatalogSearchHit,
    CatalogSource,
    CommercialPolicy,
    DeliveryFact,
    InventoryLevel,
    Product,
    ProductPrice,
    ProductVariant,
)


class CatalogSourceRepository(Protocol):
    async def get(self, *, tenant_id: UUID, source_id: UUID) -> CatalogSource | None: ...

    async def get_by_code(self, *, tenant_id: UUID, source_code: str) -> CatalogSource | None: ...

    async def upsert(self, source: CatalogSource) -> CatalogSource: ...


class ProductRepository(Protocol):
    async def get(self, *, tenant_id: UUID, product_id: UUID) -> Product | None: ...

    async def get_by_sku(self, *, tenant_id: UUID, sku: str) -> Product | None: ...

    async def list(
        self,
        *,
        tenant_id: UUID,
        category_code: str | None = None,
        status: str | None = None,
        query_text: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Product]: ...

    async def save(self, product: Product) -> Product: ...


class ProductVariantRepository(Protocol):
    async def get(self, *, tenant_id: UUID, variant_id: UUID) -> ProductVariant | None: ...

    async def get_by_sku(self, *, tenant_id: UUID, sku: str) -> ProductVariant | None: ...

    async def list_for_product(
        self, *, tenant_id: UUID, product_id: UUID
    ) -> Sequence[ProductVariant]: ...

    async def save(self, variant: ProductVariant) -> ProductVariant: ...


class ProductPriceRepository(Protocol):
    async def get_current(
        self, *, tenant_id: UUID, variant_id: UUID, at
    ) -> ProductPrice | None: ...

    async def list_for_variant(
        self, *, tenant_id: UUID, variant_id: UUID
    ) -> Sequence[ProductPrice]: ...

    async def save(self, price: ProductPrice) -> ProductPrice: ...


class InventoryLevelRepository(Protocol):
    async def get_for_location(
        self, *, tenant_id: UUID, variant_id: UUID, location_code: str
    ) -> InventoryLevel | None: ...

    async def list_for_variant(
        self, *, tenant_id: UUID, variant_id: UUID
    ) -> Sequence[InventoryLevel]: ...

    async def save(self, level: InventoryLevel) -> InventoryLevel: ...


class DeliveryFactRepository(Protocol):
    async def get_for_location(
        self, *, tenant_id: UUID, variant_id: UUID, location_code: str
    ) -> DeliveryFact | None: ...

    async def save(self, fact: DeliveryFact) -> DeliveryFact: ...


class CommercialPolicyRepository(Protocol):
    async def get(self, *, tenant_id: UUID) -> CommercialPolicy | None: ...

    async def save(self, policy: CommercialPolicy) -> CommercialPolicy: ...


class CatalogFreshnessPolicyRepository(Protocol):
    async def get(self, *, tenant_id: UUID) -> CatalogFreshnessPolicy | None: ...

    async def save(self, policy: CatalogFreshnessPolicy) -> CatalogFreshnessPolicy: ...


class CatalogImportRunRepository(Protocol):
    async def get(self, *, tenant_id: UUID, run_id: UUID) -> CatalogImportRun | None: ...

    async def list(self, *, tenant_id: UUID, limit: int = 50) -> Sequence[CatalogImportRun]: ...

    async def save(self, run: CatalogImportRun) -> CatalogImportRun: ...


class CatalogImportRowResultRepository(Protocol):
    async def list_for_run(
        self, *, tenant_id: UUID, import_run_id: UUID
    ) -> Sequence[CatalogImportRowResult]: ...

    async def replace_for_run(
        self, *, tenant_id: UUID, import_run_id: UUID, rows: Sequence[CatalogImportRowResult]
    ) -> None: ...


class CatalogSearchRepository(Protocol):
    async def search(
        self, *, tenant_id: UUID, filters: CatalogSearchFilters, now
    ) -> Sequence[CatalogSearchHit]: ...
