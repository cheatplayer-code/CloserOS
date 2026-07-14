"""SQLAlchemy repositories for product catalog (Block V1-2)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.product_catalog_freshness import (
    default_freshness_policy_values,
    evaluate_fact_freshness,
)
from closeros.domain.product_catalog import (
    CatalogEntityStatus,
    CatalogFreshnessPolicy,
    CatalogImportErrorCode,
    CatalogImportRowResult,
    CatalogImportRun,
    CatalogImportStatus,
    CatalogSearchFilters,
    CatalogSearchHit,
    CatalogSource,
    CatalogSourceKind,
    CommercialPolicy,
    DeliveryFact,
    FactVerificationStatus,
    InventoryLevel,
    PriceKind,
    Product,
    ProductPrice,
    ProductVariant,
    normalize_catalog_text,
)
from closeros.infrastructure.product_catalog_orm import (
    CatalogCommercialPolicyRow,
    CatalogDeliveryFactRow,
    CatalogFreshnessPolicyRow,
    CatalogImportRowResultRow,
    CatalogImportRunRow,
    CatalogInventoryLevelRow,
    CatalogProductPriceRow,
    CatalogProductRow,
    CatalogProductVariantRow,
    CatalogSourceRow,
)


def _source_from_row(row: CatalogSourceRow) -> CatalogSource:
    return CatalogSource(
        id=row.id,
        tenant_id=row.tenant_id,
        source_code=row.source_code,
        kind=CatalogSourceKind(row.kind),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _product_from_row(row: CatalogProductRow) -> Product:
    return Product(
        id=row.id,
        tenant_id=row.tenant_id,
        sku=row.sku,
        name=row.name,
        name_normalized=row.name_normalized,
        category_code=row.category_code,
        description=row.description,
        status=CatalogEntityStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )


def _variant_from_row(row: CatalogProductVariantRow) -> ProductVariant:
    return ProductVariant(
        id=row.id,
        tenant_id=row.tenant_id,
        product_id=row.product_id,
        sku=row.sku,
        display_name=row.display_name,
        attributes=dict(row.attributes or {}),
        status=CatalogEntityStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )


def _price_from_row(row: CatalogProductPriceRow) -> ProductPrice:
    return ProductPrice(
        id=row.id,
        tenant_id=row.tenant_id,
        variant_id=row.variant_id,
        amount_minor=row.amount_minor,
        currency=row.currency,
        price_kind=PriceKind(row.price_kind),
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        source_id=row.source_id,
        source_updated_at=row.source_updated_at,
        verification_status=FactVerificationStatus(row.verification_status),
        checked_at=row.checked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )


def _inventory_from_row(row: CatalogInventoryLevelRow) -> InventoryLevel:
    return InventoryLevel(
        id=row.id,
        tenant_id=row.tenant_id,
        variant_id=row.variant_id,
        location_code=row.location_code,
        available_quantity=row.available_quantity,
        reserved_quantity=row.reserved_quantity,
        source_id=row.source_id,
        source_updated_at=row.source_updated_at,
        verification_status=FactVerificationStatus(row.verification_status),
        checked_at=row.checked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )


def _delivery_from_row(row: CatalogDeliveryFactRow) -> DeliveryFact:
    return DeliveryFact(
        id=row.id,
        tenant_id=row.tenant_id,
        variant_id=row.variant_id,
        location_code=row.location_code,
        lead_time_hours=row.lead_time_hours,
        source_id=row.source_id,
        source_updated_at=row.source_updated_at,
        verification_status=FactVerificationStatus(row.verification_status),
        checked_at=row.checked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )


class SqlAlchemyCatalogSourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, tenant_id: UUID, source_id: UUID) -> CatalogSource | None:
        row = await self._session.get(CatalogSourceRow, source_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _source_from_row(row)

    async def get_by_code(self, *, tenant_id: UUID, source_code: str) -> CatalogSource | None:
        result = await self._session.execute(
            select(CatalogSourceRow).where(
                CatalogSourceRow.tenant_id == tenant_id,
                CatalogSourceRow.source_code == source_code,
            )
        )
        row = result.scalar_one_or_none()
        return _source_from_row(row) if row else None

    async def upsert(self, source: CatalogSource) -> CatalogSource:
        row = await self._session.get(CatalogSourceRow, source.id)
        if row is None:
            row = CatalogSourceRow(
                id=source.id,
                tenant_id=source.tenant_id,
                source_code=source.source_code,
                kind=source.kind.value,
                created_at=source.created_at,
                updated_at=source.updated_at,
            )
            self._session.add(row)
        else:
            if row.tenant_id != source.tenant_id:
                raise ValueError("cross-tenant catalog source update denied")
            row.source_code = source.source_code
            row.kind = source.kind.value
            row.updated_at = source.updated_at
        await self._session.flush()
        return source


class SqlAlchemyProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, tenant_id: UUID, product_id: UUID) -> Product | None:
        row = await self._session.get(CatalogProductRow, product_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _product_from_row(row)

    async def get_by_sku(self, *, tenant_id: UUID, sku: str) -> Product | None:
        result = await self._session.execute(
            select(CatalogProductRow).where(
                CatalogProductRow.tenant_id == tenant_id, CatalogProductRow.sku == sku
            )
        )
        row = result.scalar_one_or_none()
        return _product_from_row(row) if row else None

    async def list(
        self,
        *,
        tenant_id: UUID,
        category_code: str | None = None,
        status: str | None = None,
        query_text: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Product]:
        stmt = select(CatalogProductRow).where(CatalogProductRow.tenant_id == tenant_id)
        if category_code is not None:
            stmt = stmt.where(CatalogProductRow.category_code == category_code)
        if status is not None:
            stmt = stmt.where(CatalogProductRow.status == status)
        if query_text:
            needle = normalize_catalog_text(query_text)
            stmt = stmt.where(
                (CatalogProductRow.name_normalized.contains(needle))
                | (CatalogProductRow.sku.ilike(f"%{query_text.strip()}%"))
            )
        stmt = stmt.order_by(CatalogProductRow.name_normalized).offset(offset).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_product_from_row(row) for row in rows]

    async def save(self, product: Product) -> Product:
        row = await self._session.get(CatalogProductRow, product.id)
        if row is None:
            self._session.add(
                CatalogProductRow(
                    id=product.id,
                    tenant_id=product.tenant_id,
                    sku=product.sku,
                    name=product.name,
                    name_normalized=product.name_normalized,
                    category_code=product.category_code,
                    description=product.description,
                    status=product.status.value,
                    created_at=product.created_at,
                    updated_at=product.updated_at,
                    version=product.version,
                )
            )
        else:
            if row.tenant_id != product.tenant_id:
                raise ValueError("cross-tenant product update denied")
            if product.version <= row.version:
                from closeros.domain.product_catalog import CatalogOptimisticLockError

                raise CatalogOptimisticLockError("product version conflict")
            row.sku = product.sku
            row.name = product.name
            row.name_normalized = product.name_normalized
            row.category_code = product.category_code
            row.description = product.description
            row.status = product.status.value
            row.updated_at = product.updated_at
            row.version = product.version
        await self._session.flush()
        return product


class SqlAlchemyProductVariantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, tenant_id: UUID, variant_id: UUID) -> ProductVariant | None:
        row = await self._session.get(CatalogProductVariantRow, variant_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _variant_from_row(row)

    async def get_by_sku(self, *, tenant_id: UUID, sku: str) -> ProductVariant | None:
        result = await self._session.execute(
            select(CatalogProductVariantRow).where(
                CatalogProductVariantRow.tenant_id == tenant_id,
                CatalogProductVariantRow.sku == sku,
            )
        )
        row = result.scalar_one_or_none()
        return _variant_from_row(row) if row else None

    async def list_for_product(
        self, *, tenant_id: UUID, product_id: UUID
    ) -> Sequence[ProductVariant]:
        result = await self._session.execute(
            select(CatalogProductVariantRow).where(
                CatalogProductVariantRow.tenant_id == tenant_id,
                CatalogProductVariantRow.product_id == product_id,
            )
        )
        return [_variant_from_row(row) for row in result.scalars().all()]

    async def save(self, variant: ProductVariant) -> ProductVariant:
        row = await self._session.get(CatalogProductVariantRow, variant.id)
        if row is None:
            self._session.add(
                CatalogProductVariantRow(
                    id=variant.id,
                    tenant_id=variant.tenant_id,
                    product_id=variant.product_id,
                    sku=variant.sku,
                    display_name=variant.display_name,
                    attributes=dict(variant.attributes),
                    status=variant.status.value,
                    created_at=variant.created_at,
                    updated_at=variant.updated_at,
                    version=variant.version,
                )
            )
        else:
            if row.tenant_id != variant.tenant_id:
                raise ValueError("cross-tenant variant update denied")
            if variant.version <= row.version:
                from closeros.domain.product_catalog import CatalogOptimisticLockError

                raise CatalogOptimisticLockError("variant version conflict")
            row.sku = variant.sku
            row.display_name = variant.display_name
            row.attributes = dict(variant.attributes)
            row.status = variant.status.value
            row.updated_at = variant.updated_at
            row.version = variant.version
        await self._session.flush()
        return variant


class SqlAlchemyProductPriceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_current(
        self, *, tenant_id: UUID, variant_id: UUID, at: datetime
    ) -> ProductPrice | None:
        result = await self._session.execute(
            select(CatalogProductPriceRow)
            .where(
                CatalogProductPriceRow.tenant_id == tenant_id,
                CatalogProductPriceRow.variant_id == variant_id,
                CatalogProductPriceRow.valid_from <= at,
                (CatalogProductPriceRow.valid_until.is_(None))
                | (CatalogProductPriceRow.valid_until > at),
            )
            .order_by(CatalogProductPriceRow.valid_from.desc())
        )
        rows = list(result.scalars().all())
        if not rows:
            return None
        kind_rank = {"list": 0, "sale": 1, "promotional": 2}
        rows.sort(key=lambda r: (kind_rank.get(r.price_kind, 9), -r.valid_from.timestamp()))
        return _price_from_row(rows[0])

    async def list_for_variant(
        self, *, tenant_id: UUID, variant_id: UUID
    ) -> Sequence[ProductPrice]:
        result = await self._session.execute(
            select(CatalogProductPriceRow).where(
                CatalogProductPriceRow.tenant_id == tenant_id,
                CatalogProductPriceRow.variant_id == variant_id,
            )
        )
        return [_price_from_row(row) for row in result.scalars().all()]

    async def save(self, price: ProductPrice) -> ProductPrice:
        row = await self._session.get(CatalogProductPriceRow, price.id)
        if row is None:
            self._session.add(
                CatalogProductPriceRow(
                    id=price.id,
                    tenant_id=price.tenant_id,
                    variant_id=price.variant_id,
                    amount_minor=price.amount_minor,
                    currency=price.currency,
                    price_kind=price.price_kind.value,
                    valid_from=price.valid_from,
                    valid_until=price.valid_until,
                    source_id=price.source_id,
                    source_updated_at=price.source_updated_at,
                    verification_status=price.verification_status.value,
                    checked_at=price.checked_at,
                    created_at=price.created_at,
                    updated_at=price.updated_at,
                    version=price.version,
                )
            )
        else:
            if row.tenant_id != price.tenant_id:
                raise ValueError("cross-tenant price update denied")
            row.amount_minor = price.amount_minor
            row.currency = price.currency
            row.price_kind = price.price_kind.value
            row.valid_from = price.valid_from
            row.valid_until = price.valid_until
            row.source_id = price.source_id
            row.source_updated_at = price.source_updated_at
            row.verification_status = price.verification_status.value
            row.checked_at = price.checked_at
            row.updated_at = price.updated_at
            row.version = price.version
        await self._session.flush()
        return price


class SqlAlchemyInventoryLevelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_location(
        self, *, tenant_id: UUID, variant_id: UUID, location_code: str
    ) -> InventoryLevel | None:
        result = await self._session.execute(
            select(CatalogInventoryLevelRow).where(
                CatalogInventoryLevelRow.tenant_id == tenant_id,
                CatalogInventoryLevelRow.variant_id == variant_id,
                CatalogInventoryLevelRow.location_code == location_code,
            )
        )
        row = result.scalar_one_or_none()
        return _inventory_from_row(row) if row else None

    async def list_for_variant(
        self, *, tenant_id: UUID, variant_id: UUID
    ) -> Sequence[InventoryLevel]:
        result = await self._session.execute(
            select(CatalogInventoryLevelRow).where(
                CatalogInventoryLevelRow.tenant_id == tenant_id,
                CatalogInventoryLevelRow.variant_id == variant_id,
            )
        )
        return [_inventory_from_row(row) for row in result.scalars().all()]

    async def save(self, level: InventoryLevel) -> InventoryLevel:
        existing = await self.get_for_location(
            tenant_id=level.tenant_id,
            variant_id=level.variant_id,
            location_code=level.location_code,
        )
        row = await self._session.get(CatalogInventoryLevelRow, level.id)
        if row is None and existing is not None:
            row = await self._session.get(CatalogInventoryLevelRow, existing.id)
        if row is None:
            self._session.add(
                CatalogInventoryLevelRow(
                    id=level.id,
                    tenant_id=level.tenant_id,
                    variant_id=level.variant_id,
                    location_code=level.location_code,
                    available_quantity=level.available_quantity,
                    reserved_quantity=level.reserved_quantity,
                    source_id=level.source_id,
                    source_updated_at=level.source_updated_at,
                    verification_status=level.verification_status.value,
                    checked_at=level.checked_at,
                    created_at=level.created_at,
                    updated_at=level.updated_at,
                    version=level.version,
                )
            )
        else:
            if row.tenant_id != level.tenant_id:
                raise ValueError("cross-tenant inventory update denied")
            row.available_quantity = level.available_quantity
            row.reserved_quantity = level.reserved_quantity
            row.source_id = level.source_id
            row.source_updated_at = level.source_updated_at
            row.verification_status = level.verification_status.value
            row.checked_at = level.checked_at
            row.updated_at = level.updated_at
            row.version = level.version
        await self._session.flush()
        return level


class SqlAlchemyDeliveryFactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_location(
        self, *, tenant_id: UUID, variant_id: UUID, location_code: str
    ) -> DeliveryFact | None:
        result = await self._session.execute(
            select(CatalogDeliveryFactRow).where(
                CatalogDeliveryFactRow.tenant_id == tenant_id,
                CatalogDeliveryFactRow.variant_id == variant_id,
                CatalogDeliveryFactRow.location_code == location_code,
            )
        )
        row = result.scalar_one_or_none()
        return _delivery_from_row(row) if row else None

    async def save(self, fact: DeliveryFact) -> DeliveryFact:
        existing = await self.get_for_location(
            tenant_id=fact.tenant_id,
            variant_id=fact.variant_id,
            location_code=fact.location_code,
        )
        row = await self._session.get(CatalogDeliveryFactRow, fact.id)
        if row is None and existing is not None:
            row = await self._session.get(CatalogDeliveryFactRow, existing.id)
        if row is None:
            self._session.add(
                CatalogDeliveryFactRow(
                    id=fact.id,
                    tenant_id=fact.tenant_id,
                    variant_id=fact.variant_id,
                    location_code=fact.location_code,
                    lead_time_hours=fact.lead_time_hours,
                    source_id=fact.source_id,
                    source_updated_at=fact.source_updated_at,
                    verification_status=fact.verification_status.value,
                    checked_at=fact.checked_at,
                    created_at=fact.created_at,
                    updated_at=fact.updated_at,
                    version=fact.version,
                )
            )
        else:
            if row.tenant_id != fact.tenant_id:
                raise ValueError("cross-tenant delivery update denied")
            row.lead_time_hours = fact.lead_time_hours
            row.source_id = fact.source_id
            row.source_updated_at = fact.source_updated_at
            row.verification_status = fact.verification_status.value
            row.checked_at = fact.checked_at
            row.updated_at = fact.updated_at
            row.version = fact.version
        await self._session.flush()
        return fact


class SqlAlchemyCommercialPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, tenant_id: UUID) -> CommercialPolicy | None:
        result = await self._session.execute(
            select(CatalogCommercialPolicyRow).where(
                CatalogCommercialPolicyRow.tenant_id == tenant_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return CommercialPolicy(
            id=row.id,
            tenant_id=row.tenant_id,
            allow_discount=row.allow_discount,
            max_discount_basis_points=row.max_discount_basis_points,
            allow_hold_inventory=row.allow_hold_inventory,
            default_currency=row.default_currency,
            created_at=row.created_at,
            updated_at=row.updated_at,
            version=row.version,
        )

    async def save(self, policy: CommercialPolicy) -> CommercialPolicy:
        existing = await self.get(tenant_id=policy.tenant_id)
        row = await self._session.get(CatalogCommercialPolicyRow, policy.id)
        if row is None and existing is not None:
            row = await self._session.get(CatalogCommercialPolicyRow, existing.id)
        if row is None:
            self._session.add(
                CatalogCommercialPolicyRow(
                    id=policy.id,
                    tenant_id=policy.tenant_id,
                    allow_discount=policy.allow_discount,
                    max_discount_basis_points=policy.max_discount_basis_points,
                    allow_hold_inventory=policy.allow_hold_inventory,
                    default_currency=policy.default_currency,
                    created_at=policy.created_at,
                    updated_at=policy.updated_at,
                    version=policy.version,
                )
            )
        else:
            row.allow_discount = policy.allow_discount
            row.max_discount_basis_points = policy.max_discount_basis_points
            row.allow_hold_inventory = policy.allow_hold_inventory
            row.default_currency = policy.default_currency
            row.updated_at = policy.updated_at
            row.version = policy.version
        await self._session.flush()
        return policy


class SqlAlchemyCatalogFreshnessPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, tenant_id: UUID) -> CatalogFreshnessPolicy | None:
        result = await self._session.execute(
            select(CatalogFreshnessPolicyRow).where(
                CatalogFreshnessPolicyRow.tenant_id == tenant_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return CatalogFreshnessPolicy(
            id=row.id,
            tenant_id=row.tenant_id,
            inventory_ttl_seconds=row.inventory_ttl_seconds,
            price_ttl_seconds=row.price_ttl_seconds,
            delivery_ttl_seconds=row.delivery_ttl_seconds,
            promotion_ttl_seconds=row.promotion_ttl_seconds,
            description_ttl_seconds=row.description_ttl_seconds,
            created_at=row.created_at,
            updated_at=row.updated_at,
            version=row.version,
        )

    async def save(self, policy: CatalogFreshnessPolicy) -> CatalogFreshnessPolicy:
        existing = await self.get(tenant_id=policy.tenant_id)
        row = await self._session.get(CatalogFreshnessPolicyRow, policy.id)
        if row is None and existing is not None:
            row = await self._session.get(CatalogFreshnessPolicyRow, existing.id)
        if row is None:
            self._session.add(
                CatalogFreshnessPolicyRow(
                    id=policy.id,
                    tenant_id=policy.tenant_id,
                    inventory_ttl_seconds=policy.inventory_ttl_seconds,
                    price_ttl_seconds=policy.price_ttl_seconds,
                    delivery_ttl_seconds=policy.delivery_ttl_seconds,
                    promotion_ttl_seconds=policy.promotion_ttl_seconds,
                    description_ttl_seconds=policy.description_ttl_seconds,
                    created_at=policy.created_at,
                    updated_at=policy.updated_at,
                    version=policy.version,
                )
            )
        else:
            row.inventory_ttl_seconds = policy.inventory_ttl_seconds
            row.price_ttl_seconds = policy.price_ttl_seconds
            row.delivery_ttl_seconds = policy.delivery_ttl_seconds
            row.promotion_ttl_seconds = policy.promotion_ttl_seconds
            row.description_ttl_seconds = policy.description_ttl_seconds
            row.updated_at = policy.updated_at
            row.version = policy.version
        await self._session.flush()
        return policy


class SqlAlchemyCatalogImportRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _from_row(self, row: CatalogImportRunRow) -> CatalogImportRun:
        return CatalogImportRun(
            id=row.id,
            tenant_id=row.tenant_id,
            source_id=row.source_id,
            creator_user_id=row.creator_user_id,
            status=CatalogImportStatus(row.status),
            delimiter=row.delimiter,
            payload_sha256=bytes(row.payload_sha256),
            payload_bytes=row.payload_bytes,
            mapping_json=dict(row.mapping_json) if row.mapping_json else None,
            total_rows=row.total_rows,
            valid_rows=row.valid_rows,
            invalid_rows=row.invalid_rows,
            created_count=row.created_count,
            updated_count=row.updated_count,
            skipped_count=row.skipped_count,
            failed_count=row.failed_count,
            created_at=row.created_at,
            updated_at=row.updated_at,
            published_at=row.published_at,
            version=row.version,
        )

    async def get(self, *, tenant_id: UUID, run_id: UUID) -> CatalogImportRun | None:
        row = await self._session.get(CatalogImportRunRow, run_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return self._from_row(row)

    async def list(self, *, tenant_id: UUID, limit: int = 50) -> Sequence[CatalogImportRun]:
        result = await self._session.execute(
            select(CatalogImportRunRow)
            .where(CatalogImportRunRow.tenant_id == tenant_id)
            .order_by(CatalogImportRunRow.created_at.desc())
            .limit(limit)
        )
        return [self._from_row(row) for row in result.scalars().all()]

    async def save(self, run: CatalogImportRun) -> CatalogImportRun:
        row = await self._session.get(CatalogImportRunRow, run.id)
        if row is None:
            self._session.add(
                CatalogImportRunRow(
                    id=run.id,
                    tenant_id=run.tenant_id,
                    source_id=run.source_id,
                    creator_user_id=run.creator_user_id,
                    status=run.status.value,
                    delimiter=run.delimiter,
                    payload_sha256=run.payload_sha256,
                    payload_bytes=run.payload_bytes,
                    mapping_json=dict(run.mapping_json) if run.mapping_json else None,
                    total_rows=run.total_rows,
                    valid_rows=run.valid_rows,
                    invalid_rows=run.invalid_rows,
                    created_count=run.created_count,
                    updated_count=run.updated_count,
                    skipped_count=run.skipped_count,
                    failed_count=run.failed_count,
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                    published_at=run.published_at,
                    version=run.version,
                )
            )
        else:
            if row.tenant_id != run.tenant_id:
                raise ValueError("cross-tenant import run update denied")
            row.status = run.status.value
            row.mapping_json = dict(run.mapping_json) if run.mapping_json else None
            row.total_rows = run.total_rows
            row.valid_rows = run.valid_rows
            row.invalid_rows = run.invalid_rows
            row.created_count = run.created_count
            row.updated_count = run.updated_count
            row.skipped_count = run.skipped_count
            row.failed_count = run.failed_count
            row.updated_at = run.updated_at
            row.published_at = run.published_at
            row.version = run.version
        await self._session.flush()
        return run


class SqlAlchemyCatalogImportRowResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _from_row(self, row: CatalogImportRowResultRow) -> CatalogImportRowResult:
        return CatalogImportRowResult(
            id=row.id,
            tenant_id=row.tenant_id,
            import_run_id=row.import_run_id,
            row_number=row.row_number,
            source_row_key=row.source_row_key,
            is_valid=row.is_valid,
            error_code=CatalogImportErrorCode(row.error_code) if row.error_code else None,
            error_message=row.error_message,
            normalized_payload=dict(row.normalized_payload) if row.normalized_payload else None,
            created_at=row.created_at,
        )

    async def list_for_run(
        self, *, tenant_id: UUID, import_run_id: UUID
    ) -> Sequence[CatalogImportRowResult]:
        result = await self._session.execute(
            select(CatalogImportRowResultRow)
            .where(
                CatalogImportRowResultRow.tenant_id == tenant_id,
                CatalogImportRowResultRow.import_run_id == import_run_id,
            )
            .order_by(CatalogImportRowResultRow.row_number)
        )
        return [self._from_row(row) for row in result.scalars().all()]

    async def replace_for_run(
        self,
        *,
        tenant_id: UUID,
        import_run_id: UUID,
        rows: Sequence[CatalogImportRowResult],
    ) -> None:
        await self._session.execute(
            delete(CatalogImportRowResultRow).where(
                CatalogImportRowResultRow.tenant_id == tenant_id,
                CatalogImportRowResultRow.import_run_id == import_run_id,
            )
        )
        for item in rows:
            if item.tenant_id != tenant_id or item.import_run_id != import_run_id:
                raise ValueError("import row tenant mismatch")
            self._session.add(
                CatalogImportRowResultRow(
                    id=item.id,
                    tenant_id=item.tenant_id,
                    import_run_id=item.import_run_id,
                    row_number=item.row_number,
                    source_row_key=item.source_row_key,
                    is_valid=item.is_valid,
                    error_code=item.error_code.value if item.error_code else None,
                    error_message=item.error_message,
                    normalized_payload=(
                        dict(item.normalized_payload) if item.normalized_payload else None
                    ),
                    created_at=item.created_at,
                )
            )
        await self._session.flush()


class SqlAlchemyCatalogSearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._prices = SqlAlchemyProductPriceRepository(session)
        self._inventory = SqlAlchemyInventoryLevelRepository(session)
        self._delivery = SqlAlchemyDeliveryFactRepository(session)
        self._freshness = SqlAlchemyCatalogFreshnessPolicyRepository(session)

    async def search(
        self, *, tenant_id: UUID, filters: CatalogSearchFilters, now: datetime
    ) -> Sequence[CatalogSearchHit]:
        freshness = await self._freshness.get(tenant_id=tenant_id)
        ttl = (
            {
                "price": freshness.price_ttl_seconds,
                "inventory": freshness.inventory_ttl_seconds,
                "delivery": freshness.delivery_ttl_seconds,
            }
            if freshness
            else {
                "price": default_freshness_policy_values()["price_ttl_seconds"],
                "inventory": default_freshness_policy_values()["inventory_ttl_seconds"],
                "delivery": default_freshness_policy_values()["delivery_ttl_seconds"],
            }
        )

        product_stmt = select(CatalogProductRow).where(CatalogProductRow.tenant_id == tenant_id)
        if filters.category is not None:
            product_stmt = product_stmt.where(CatalogProductRow.category_code == filters.category)
        if filters.product_status is not None:
            product_stmt = product_stmt.where(
                CatalogProductRow.status == filters.product_status.value
            )
        if filters.query_text:
            needle = normalize_catalog_text(filters.query_text)
            product_stmt = product_stmt.where(
                (CatalogProductRow.name_normalized.contains(needle))
                | (CatalogProductRow.sku.ilike(f"%{filters.query_text.strip()}%"))
            )
        products = {
            row.id: row for row in (await self._session.execute(product_stmt)).scalars().all()
        }
        if not products:
            return []

        variant_stmt = select(CatalogProductVariantRow).where(
            CatalogProductVariantRow.tenant_id == tenant_id,
            CatalogProductVariantRow.product_id.in_(tuple(products.keys())),
        )
        if filters.variant_status is not None:
            variant_stmt = variant_stmt.where(
                CatalogProductVariantRow.status == filters.variant_status.value
            )
        variants = list((await self._session.execute(variant_stmt)).scalars().all())

        hits: list[CatalogSearchHit] = []
        for variant in variants:
            attrs = dict(variant.attributes or {})
            if filters.color:
                color_norm = normalize_catalog_text(filters.color)
                if normalize_catalog_text(attrs.get("color", "")) != color_norm:
                    continue
            if filters.material and normalize_catalog_text(
                attrs.get("material", "")
            ) != normalize_catalog_text(filters.material):
                continue
            if filters.dimensions and normalize_catalog_text(
                attrs.get("dimensions", "")
            ) != normalize_catalog_text(filters.dimensions):
                continue

            price = await self._prices.get_current(
                tenant_id=tenant_id, variant_id=variant.id, at=now
            )
            if price is None:
                continue
            if filters.currency and price.currency != filters.currency:
                continue
            if (
                filters.budget_min_minor is not None
                and price.amount_minor < filters.budget_min_minor
            ):
                continue
            if (
                filters.budget_max_minor is not None
                and price.amount_minor > filters.budget_max_minor
            ):
                continue

            inventory_levels = await self._inventory.list_for_variant(
                tenant_id=tenant_id, variant_id=variant.id
            )
            if filters.location:
                inventory_levels = [
                    level for level in inventory_levels if level.location_code == filters.location
                ]
            if not inventory_levels:
                continue
            inventory = max(
                inventory_levels,
                key=lambda level: level.available_quantity - level.reserved_quantity,
            )
            sellable = inventory.available_quantity - inventory.reserved_quantity
            if filters.in_stock_only and sellable <= 0:
                continue

            delivery = None
            if filters.location:
                delivery = await self._delivery.get_for_location(
                    tenant_id=tenant_id,
                    variant_id=variant.id,
                    location_code=filters.location,
                )

            price_prov = evaluate_fact_freshness(
                verification_status=price.verification_status,
                source_updated_at=price.source_updated_at,
                checked_at=price.checked_at,
                ttl_seconds=ttl["price"],
                now=now,
                source_id=price.source_id,
            )
            inv_prov = evaluate_fact_freshness(
                verification_status=inventory.verification_status,
                source_updated_at=inventory.source_updated_at,
                checked_at=inventory.checked_at,
                ttl_seconds=ttl["inventory"],
                now=now,
                source_id=inventory.source_id,
            )
            delivery_usable = False
            delivery_status = None
            if delivery is not None:
                delivery_prov = evaluate_fact_freshness(
                    verification_status=delivery.verification_status,
                    source_updated_at=delivery.source_updated_at,
                    checked_at=delivery.checked_at,
                    ttl_seconds=ttl["delivery"],
                    now=now,
                    source_id=delivery.source_id,
                )
                delivery_usable = delivery_prov.usable
                delivery_status = delivery_prov.verification_status

            product = products[variant.product_id]
            hits.append(
                CatalogSearchHit(
                    product_id=product.id,
                    variant_id=variant.id,
                    product_sku=product.sku,
                    variant_sku=variant.sku,
                    product_name=product.name,
                    variant_display_name=variant.display_name,
                    category_code=product.category_code,
                    amount_minor=price.amount_minor,
                    currency=price.currency,
                    available_quantity=sellable,
                    in_stock=sellable > 0,
                    attributes=attrs,
                    price_provenance=price_prov,
                    inventory_provenance=inv_prov,
                    delivery_status=delivery_status,
                    delivery_usable=delivery_usable,
                )
            )
            if len(hits) >= filters.limit:
                break
        return hits
