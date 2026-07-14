"""Application service for product catalog CRUD, import, search, and commercial actions."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.clock import Clock, SystemClock
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.product_catalog_audit import (
    catalog_fact_queried_event,
    catalog_import_event,
    catalog_product_mutated_event,
)
from closeros.application.product_catalog_csv import parse_catalog_csv
from closeros.application.product_catalog_freshness import (
    default_freshness_policy_values,
    evaluate_fact_freshness,
)
from closeros.application.tenant_context import TenantContext
from closeros.domain.audit import AuditAction, AuditActorType
from closeros.domain.identity import Role
from closeros.domain.product_catalog import (
    CatalogAuthorizationError,
    CatalogDomainError,
    CatalogEntityStatus,
    CatalogFreshnessPolicy,
    CatalogImportRun,
    CatalogImportStatus,
    CatalogSearchFilters,
    CatalogSearchHit,
    CatalogSource,
    CatalogSourceKind,
    CommercialActionCode,
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

_MANAGE_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD})
# Managers do not mutate catalog facts unless an explicit future policy grants it.
_READ_ROLES = frozenset(
    {Role.OWNER, Role.SALES_HEAD, Role.MANAGER, Role.ANALYST, Role.COMPLIANCE_ADMIN}
)


def _require_manage(context: TenantContext) -> None:
    if not context.membership.roles.intersection(_MANAGE_ROLES):
        raise CatalogAuthorizationError("catalog mutation requires owner or sales_head")


def _require_read(context: TenantContext) -> None:
    if not context.membership.roles.intersection(_READ_ROLES):
        raise CatalogAuthorizationError("catalog read denied")


class ProductCatalogService:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], IntegratedUnitOfWork],
        clock: Clock | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock or SystemClock()

    async def ensure_manual_source(
        self, *, context: TenantContext, uow: IntegratedUnitOfWork
    ) -> CatalogSource:
        existing = await uow.catalog_sources.get_by_code(
            tenant_id=context.tenant.id, source_code="manual"
        )
        if existing is not None:
            return existing
        now = self._clock.now()
        source = CatalogSource(
            id=uuid4(),
            tenant_id=context.tenant.id,
            source_code="manual",
            kind=CatalogSourceKind.MANUAL,
            created_at=now,
            updated_at=now,
        )
        return await uow.catalog_sources.upsert(source)

    async def create_product_draft(
        self,
        *,
        context: TenantContext,
        sku: str,
        name: str,
        category_code: str,
        description: str = "",
        audit_context: AuditContext,
    ) -> Product:
        _require_manage(context)
        now = self._clock.now()
        product = Product(
            id=uuid4(),
            tenant_id=context.tenant.id,
            sku=sku,
            name=name,
            name_normalized=normalize_catalog_text(name),
            category_code=category_code,
            description=description,
            status=CatalogEntityStatus.DRAFT,
            created_at=now,
            updated_at=now,
            version=1,
        )
        async with self._uow_factory() as uow:
            existing = await uow.catalog_products.get_by_sku(
                tenant_id=context.tenant.id, sku=product.sku
            )
            if existing is not None:
                raise CatalogDomainError("product sku already exists")
            await uow.catalog_products.save(product)
            await append_required_audit_event(
                uow.audit_events,
                catalog_product_mutated_event(
                    tenant_id=context.tenant.id,
                    product_id=product.id,
                    action=AuditAction.CATALOG_PRODUCT_CREATED,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=uuid4(),
                    status=product.status.value,
                    category_code=product.category_code,
                ),
            )
            await uow.commit()
        return product

    async def update_product(
        self,
        *,
        context: TenantContext,
        product_id: UUID,
        expected_version: int,
        name: str | None = None,
        category_code: str | None = None,
        description: str | None = None,
        audit_context: AuditContext,
    ) -> Product:
        _require_manage(context)
        now = self._clock.now()
        async with self._uow_factory() as uow:
            current = await uow.catalog_products.get(
                tenant_id=context.tenant.id, product_id=product_id
            )
            if current is None:
                raise CatalogDomainError("product not found")
            if current.version != expected_version:
                from closeros.domain.product_catalog import CatalogOptimisticLockError

                raise CatalogOptimisticLockError("product version conflict")
            updated = Product(
                id=current.id,
                tenant_id=current.tenant_id,
                sku=current.sku,
                name=name if name is not None else current.name,
                name_normalized=normalize_catalog_text(name if name is not None else current.name),
                category_code=category_code if category_code is not None else current.category_code,
                description=description if description is not None else current.description,
                status=current.status,
                created_at=current.created_at,
                updated_at=now,
                version=current.version + 1,
            )
            await uow.catalog_products.save(updated)
            await append_required_audit_event(
                uow.audit_events,
                catalog_product_mutated_event(
                    tenant_id=context.tenant.id,
                    product_id=updated.id,
                    action=AuditAction.CATALOG_PRODUCT_UPDATED,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=uuid4(),
                    status=updated.status.value,
                    category_code=updated.category_code,
                ),
            )
            await uow.commit()
        return updated

    async def add_variant(
        self,
        *,
        context: TenantContext,
        product_id: UUID,
        sku: str,
        display_name: str,
        attributes: dict[str, str] | None = None,
        audit_context: AuditContext,
    ) -> ProductVariant:
        _require_manage(context)
        now = self._clock.now()
        variant = ProductVariant(
            id=uuid4(),
            tenant_id=context.tenant.id,
            product_id=product_id,
            sku=sku,
            display_name=display_name,
            attributes=attributes or {},
            status=CatalogEntityStatus.DRAFT,
            created_at=now,
            updated_at=now,
            version=1,
        )
        async with self._uow_factory() as uow:
            product = await uow.catalog_products.get(
                tenant_id=context.tenant.id, product_id=product_id
            )
            if product is None:
                raise CatalogDomainError("product not found")
            if await uow.catalog_variants.get_by_sku(tenant_id=context.tenant.id, sku=sku):
                raise CatalogDomainError("variant sku already exists")
            await uow.catalog_variants.save(variant)
            await append_required_audit_event(
                uow.audit_events,
                catalog_product_mutated_event(
                    tenant_id=context.tenant.id,
                    product_id=product_id,
                    action=AuditAction.CATALOG_VARIANT_CREATED,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=uuid4(),
                    status=variant.status.value,
                ),
            )
            await uow.commit()
        return variant

    async def set_price(
        self,
        *,
        context: TenantContext,
        variant_id: UUID,
        amount_minor: int,
        currency: str,
        price_kind: PriceKind = PriceKind.LIST,
        verification_status: FactVerificationStatus = FactVerificationStatus.VERIFIED,
        audit_context: AuditContext,
    ) -> ProductPrice:
        _require_manage(context)
        now = self._clock.now()
        async with self._uow_factory() as uow:
            variant = await uow.catalog_variants.get(
                tenant_id=context.tenant.id, variant_id=variant_id
            )
            if variant is None:
                raise CatalogDomainError("variant not found")
            source = await self.ensure_manual_source(context=context, uow=uow)
            price = ProductPrice(
                id=uuid4(),
                tenant_id=context.tenant.id,
                variant_id=variant_id,
                amount_minor=amount_minor,
                currency=currency,
                price_kind=price_kind,
                valid_from=now,
                valid_until=None,
                source_id=source.id,
                source_updated_at=now,
                verification_status=verification_status,
                checked_at=now,
                created_at=now,
                updated_at=now,
                version=1,
            )
            await uow.catalog_prices.save(price)
            await append_required_audit_event(
                uow.audit_events,
                catalog_product_mutated_event(
                    tenant_id=context.tenant.id,
                    product_id=variant.product_id,
                    action=AuditAction.CATALOG_PRICE_SET,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=uuid4(),
                    status=verification_status.value,
                ),
            )
            await uow.commit()
        return price

    async def set_inventory(
        self,
        *,
        context: TenantContext,
        variant_id: UUID,
        location_code: str,
        available_quantity: int,
        reserved_quantity: int = 0,
        verification_status: FactVerificationStatus = FactVerificationStatus.LIVE,
        audit_context: AuditContext,
    ) -> InventoryLevel:
        _require_manage(context)
        now = self._clock.now()
        async with self._uow_factory() as uow:
            variant = await uow.catalog_variants.get(
                tenant_id=context.tenant.id, variant_id=variant_id
            )
            if variant is None:
                raise CatalogDomainError("variant not found")
            source = await self.ensure_manual_source(context=context, uow=uow)
            level = InventoryLevel(
                id=uuid4(),
                tenant_id=context.tenant.id,
                variant_id=variant_id,
                location_code=location_code,
                available_quantity=available_quantity,
                reserved_quantity=reserved_quantity,
                source_id=source.id,
                source_updated_at=now,
                verification_status=verification_status,
                checked_at=now,
                created_at=now,
                updated_at=now,
                version=1,
            )
            await uow.catalog_inventory.save(level)
            await append_required_audit_event(
                uow.audit_events,
                catalog_product_mutated_event(
                    tenant_id=context.tenant.id,
                    product_id=variant.product_id,
                    action=AuditAction.CATALOG_INVENTORY_SET,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=uuid4(),
                    status=verification_status.value,
                ),
            )
            await uow.commit()
        return level

    async def publish_product(
        self,
        *,
        context: TenantContext,
        product_id: UUID,
        expected_version: int,
        audit_context: AuditContext,
    ) -> Product:
        _require_manage(context)
        now = self._clock.now()
        async with self._uow_factory() as uow:
            product = await uow.catalog_products.get(
                tenant_id=context.tenant.id, product_id=product_id
            )
            if product is None:
                raise CatalogDomainError("product not found")
            if product.version != expected_version:
                from closeros.domain.product_catalog import CatalogOptimisticLockError

                raise CatalogOptimisticLockError("product version conflict")
            variants = await uow.catalog_variants.list_for_product(
                tenant_id=context.tenant.id, product_id=product_id
            )
            if not variants:
                raise CatalogDomainError("cannot publish product without variants")
            usable_variant = False
            for variant in variants:
                price = await uow.catalog_prices.get_current(
                    tenant_id=context.tenant.id, variant_id=variant.id, at=now
                )
                levels = await uow.catalog_inventory.list_for_variant(
                    tenant_id=context.tenant.id, variant_id=variant.id
                )
                if price is None or not levels:
                    continue
                freshness = await uow.catalog_freshness_policies.get(tenant_id=context.tenant.id)
                price_ttl = (
                    freshness.price_ttl_seconds
                    if freshness
                    else default_freshness_policy_values()["price_ttl_seconds"]
                )
                inv_ttl = (
                    freshness.inventory_ttl_seconds
                    if freshness
                    else default_freshness_policy_values()["inventory_ttl_seconds"]
                )
                price_ok = evaluate_fact_freshness(
                    verification_status=price.verification_status,
                    source_updated_at=price.source_updated_at,
                    checked_at=price.checked_at,
                    ttl_seconds=price_ttl,
                    now=now,
                    source_id=price.source_id,
                ).usable
                inv_ok = any(
                    evaluate_fact_freshness(
                        verification_status=level.verification_status,
                        source_updated_at=level.source_updated_at,
                        checked_at=level.checked_at,
                        ttl_seconds=inv_ttl,
                        now=now,
                        source_id=level.source_id,
                    ).usable
                    for level in levels
                )
                if price_ok and inv_ok:
                    usable_variant = True
                    published_variant = ProductVariant(
                        id=variant.id,
                        tenant_id=variant.tenant_id,
                        product_id=variant.product_id,
                        sku=variant.sku,
                        display_name=variant.display_name,
                        attributes=variant.attributes,
                        status=CatalogEntityStatus.ACTIVE,
                        created_at=variant.created_at,
                        updated_at=now,
                        version=variant.version + 1,
                    )
                    await uow.catalog_variants.save(published_variant)
            if not usable_variant:
                raise CatalogDomainError(
                    "cannot publish while price/inventory remain unverified or unusable"
                )
            published = Product(
                id=product.id,
                tenant_id=product.tenant_id,
                sku=product.sku,
                name=product.name,
                name_normalized=product.name_normalized,
                category_code=product.category_code,
                description=product.description,
                status=CatalogEntityStatus.ACTIVE,
                created_at=product.created_at,
                updated_at=now,
                version=product.version + 1,
            )
            await uow.catalog_products.save(published)
            await append_required_audit_event(
                uow.audit_events,
                catalog_product_mutated_event(
                    tenant_id=context.tenant.id,
                    product_id=published.id,
                    action=AuditAction.CATALOG_PRODUCT_PUBLISHED,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=uuid4(),
                    status=published.status.value,
                    category_code=published.category_code,
                ),
            )
            await uow.commit()
        return published

    async def deactivate_or_archive(
        self,
        *,
        context: TenantContext,
        product_id: UUID,
        expected_version: int,
        status: CatalogEntityStatus,
        audit_context: AuditContext,
    ) -> Product:
        _require_manage(context)
        if status not in {CatalogEntityStatus.INACTIVE, CatalogEntityStatus.ARCHIVED}:
            raise CatalogDomainError("unsupported status transition")
        now = self._clock.now()
        async with self._uow_factory() as uow:
            product = await uow.catalog_products.get(
                tenant_id=context.tenant.id, product_id=product_id
            )
            if product is None:
                raise CatalogDomainError("product not found")
            if product.version != expected_version:
                from closeros.domain.product_catalog import CatalogOptimisticLockError

                raise CatalogOptimisticLockError("product version conflict")
            updated = Product(
                id=product.id,
                tenant_id=product.tenant_id,
                sku=product.sku,
                name=product.name,
                name_normalized=product.name_normalized,
                category_code=product.category_code,
                description=product.description,
                status=status,
                created_at=product.created_at,
                updated_at=now,
                version=product.version + 1,
            )
            await uow.catalog_products.save(updated)
            await append_required_audit_event(
                uow.audit_events,
                catalog_product_mutated_event(
                    tenant_id=context.tenant.id,
                    product_id=updated.id,
                    action=AuditAction.CATALOG_PRODUCT_STATUS_CHANGED,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=uuid4(),
                    status=status.value,
                ),
            )
            await uow.commit()
        return updated

    async def list_products(
        self,
        *,
        context: TenantContext,
        category_code: str | None = None,
        status: str | None = None,
        query_text: str | None = None,
        limit: int = 50,
    ) -> Sequence[Product]:
        _require_read(context)
        async with self._uow_factory() as uow:
            return await uow.catalog_products.list(
                tenant_id=context.tenant.id,
                category_code=category_code,
                status=status,
                query_text=query_text,
                limit=limit,
            )

    async def get_product_details(
        self, *, context: TenantContext, product_id: UUID
    ) -> dict[str, Any]:
        _require_read(context)
        async with self._uow_factory() as uow:
            product = await uow.catalog_products.get(
                tenant_id=context.tenant.id, product_id=product_id
            )
            if product is None:
                raise CatalogDomainError("product not found")
            variants = await uow.catalog_variants.list_for_product(
                tenant_id=context.tenant.id, product_id=product_id
            )
            return {"product": product, "variants": list(variants)}

    async def search_products(
        self,
        *,
        context: TenantContext,
        filters: CatalogSearchFilters,
        audit_context: AuditContext | None = None,
    ) -> Sequence[CatalogSearchHit]:
        _require_read(context)
        now = self._clock.now()
        async with self._uow_factory() as uow:
            hits = await uow.catalog_search.search(
                tenant_id=context.tenant.id, filters=filters, now=now
            )
            if audit_context is not None:
                for hit in hits[:5]:
                    await append_required_audit_event(
                        uow.audit_events,
                        catalog_fact_queried_event(
                            tenant_id=context.tenant.id,
                            product_id=hit.product_id,
                            occurred_at=now,
                            audit_context=audit_context,
                            actor_type=AuditActorType.USER,
                            actor_id=context.user.id,
                            event_id=uuid4(),
                            purpose_code="catalog_search",
                        ),
                    )
                await uow.commit()
        return hits

    async def check_price_and_inventory(
        self,
        *,
        context: TenantContext,
        variant_id: UUID,
        location_code: str | None = None,
    ) -> dict[str, Any]:
        _require_read(context)
        now = self._clock.now()
        async with self._uow_factory() as uow:
            variant = await uow.catalog_variants.get(
                tenant_id=context.tenant.id, variant_id=variant_id
            )
            if variant is None:
                raise CatalogDomainError("variant not found")
            price = await uow.catalog_prices.get_current(
                tenant_id=context.tenant.id, variant_id=variant_id, at=now
            )
            levels = await uow.catalog_inventory.list_for_variant(
                tenant_id=context.tenant.id, variant_id=variant_id
            )
            if location_code:
                levels = [level for level in levels if level.location_code == location_code]
            return {"variant": variant, "price": price, "inventory": levels, "checked_at": now}

    async def get_allowed_commercial_actions(
        self, *, context: TenantContext
    ) -> Sequence[CommercialActionCode]:
        _require_read(context)
        async with self._uow_factory() as uow:
            policy = await uow.catalog_commercial_policies.get(tenant_id=context.tenant.id)
        actions = [
            CommercialActionCode.QUOTE_LIST_PRICE,
            CommercialActionCode.CONFIRM_AVAILABILITY,
            CommercialActionCode.QUOTE_DELIVERY,
            CommercialActionCode.ESCALATE_TO_HUMAN,
        ]
        if policy and policy.allow_discount:
            actions.append(CommercialActionCode.OFFER_DISCOUNT)
        if policy and policy.allow_hold_inventory:
            actions.append(CommercialActionCode.HOLD_INVENTORY)
        return actions

    async def upload_csv_import(
        self,
        *,
        context: TenantContext,
        payload: bytes,
        delimiter: str,
        mapping: dict[str, str],
        audit_context: AuditContext,
        dry_run: bool = False,
    ) -> Any:
        _require_manage(context)
        now = self._clock.now()
        run_id = uuid4()
        parsed = parse_catalog_csv(
            tenant_id=context.tenant.id,
            import_run_id=run_id,
            payload=payload,
            delimiter=delimiter,
            mapping=mapping,
            now=now,
        )
        status = (
            CatalogImportStatus.READY_TO_PUBLISH
            if parsed.invalid_rows == 0 and parsed.valid_rows > 0
            else CatalogImportStatus.VALIDATION_FAILED
        )
        if dry_run:
            return {
                "dry_run": True,
                "status": status.value,
                "total_rows": parsed.total_rows,
                "valid_rows": parsed.valid_rows,
                "invalid_rows": parsed.invalid_rows,
                "rows": parsed.rows,
            }
        async with self._uow_factory() as uow:
            source = await uow.catalog_sources.get_by_code(
                tenant_id=context.tenant.id, source_code="csv_import"
            )
            if source is None:
                source = CatalogSource(
                    id=uuid4(),
                    tenant_id=context.tenant.id,
                    source_code="csv_import",
                    kind=CatalogSourceKind.CSV_IMPORT,
                    created_at=now,
                    updated_at=now,
                )
                await uow.catalog_sources.upsert(source)
            run = CatalogImportRun(
                id=run_id,
                tenant_id=context.tenant.id,
                source_id=source.id,
                creator_user_id=context.user.id,
                status=status,
                delimiter=delimiter,
                payload_sha256=parsed.payload_sha256,
                payload_bytes=parsed.payload_bytes,
                mapping_json=mapping,
                total_rows=parsed.total_rows,
                valid_rows=parsed.valid_rows,
                invalid_rows=parsed.invalid_rows,
                created_count=0,
                updated_count=0,
                skipped_count=0,
                failed_count=0,
                created_at=now,
                updated_at=now,
                published_at=None,
                version=1,
            )
            await uow.catalog_import_runs.save(run)
            await uow.catalog_import_row_results.replace_for_run(
                tenant_id=context.tenant.id, import_run_id=run_id, rows=parsed.rows
            )
            await append_required_audit_event(
                uow.audit_events,
                catalog_import_event(
                    tenant_id=context.tenant.id,
                    run_id=run_id,
                    action=AuditAction.CATALOG_IMPORT_UPLOADED,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=uuid4(),
                    status=status.value,
                    affected_count=parsed.total_rows,
                ),
            )
            await uow.commit()
        return run

    async def publish_csv_import(
        self,
        *,
        context: TenantContext,
        run_id: UUID,
        audit_context: AuditContext,
    ) -> Any:
        _require_manage(context)
        now = self._clock.now()
        async with self._uow_factory() as uow:
            run = await uow.catalog_import_runs.get(tenant_id=context.tenant.id, run_id=run_id)
            if run is None:
                raise CatalogDomainError("import run not found")
            if run.status is not CatalogImportStatus.READY_TO_PUBLISH:
                raise CatalogDomainError("import run is not ready to publish")
            rows = await uow.catalog_import_row_results.list_for_run(
                tenant_id=context.tenant.id, import_run_id=run_id
            )
            created = updated = skipped = failed = 0
            publishing = replace(
                run,
                status=CatalogImportStatus.PUBLISHING,
                updated_at=now,
                version=run.version + 1,
            )
            await uow.catalog_import_runs.save(publishing)
            try:
                for row in rows:
                    if not row.is_valid or not row.normalized_payload:
                        failed += 1
                        continue
                    payload = row.normalized_payload
                    product_sku = str(payload["product_sku"])
                    existing_product = await uow.catalog_products.get_by_sku(
                        tenant_id=context.tenant.id, sku=product_sku
                    )
                    if existing_product is None:
                        product = Product(
                            id=uuid4(),
                            tenant_id=context.tenant.id,
                            sku=product_sku,
                            name=str(payload["product_name"]),
                            name_normalized=normalize_catalog_text(str(payload["product_name"])),
                            category_code=str(payload["category_code"]),
                            description=str(payload.get("description") or ""),
                            status=CatalogEntityStatus.ACTIVE,
                            created_at=now,
                            updated_at=now,
                            version=1,
                        )
                        await uow.catalog_products.save(product)
                        created += 1
                    else:
                        product = Product(
                            id=existing_product.id,
                            tenant_id=existing_product.tenant_id,
                            sku=existing_product.sku,
                            name=str(payload["product_name"]),
                            name_normalized=normalize_catalog_text(str(payload["product_name"])),
                            category_code=str(payload["category_code"]),
                            description=str(
                                payload.get("description") or existing_product.description
                            ),
                            status=CatalogEntityStatus.ACTIVE,
                            created_at=existing_product.created_at,
                            updated_at=now,
                            version=existing_product.version + 1,
                        )
                        await uow.catalog_products.save(product)
                        updated += 1

                    variant_sku = str(payload["variant_sku"])
                    attrs: dict[str, str] = {}
                    for key in ("color", "material", "dimensions"):
                        if key in payload:
                            attrs[key] = str(payload[key])
                    existing_variant = await uow.catalog_variants.get_by_sku(
                        tenant_id=context.tenant.id, sku=variant_sku
                    )
                    if existing_variant is None:
                        variant = ProductVariant(
                            id=uuid4(),
                            tenant_id=context.tenant.id,
                            product_id=product.id,
                            sku=variant_sku,
                            display_name=str(
                                payload.get("display_name") or payload["product_name"]
                            ),
                            attributes=attrs,
                            status=CatalogEntityStatus.ACTIVE,
                            created_at=now,
                            updated_at=now,
                            version=1,
                        )
                        await uow.catalog_variants.save(variant)
                    else:
                        variant = ProductVariant(
                            id=existing_variant.id,
                            tenant_id=existing_variant.tenant_id,
                            product_id=product.id,
                            sku=existing_variant.sku,
                            display_name=str(
                                payload.get("display_name") or existing_variant.display_name
                            ),
                            attributes=attrs or dict(existing_variant.attributes),
                            status=CatalogEntityStatus.ACTIVE,
                            created_at=existing_variant.created_at,
                            updated_at=now,
                            version=existing_variant.version + 1,
                        )
                        await uow.catalog_variants.save(variant)

                    await uow.catalog_prices.save(
                        ProductPrice(
                            id=uuid4(),
                            tenant_id=context.tenant.id,
                            variant_id=variant.id,
                            amount_minor=int(str(payload["amount_minor"])),
                            currency=str(payload["currency"]),
                            price_kind=PriceKind.LIST,
                            valid_from=now,
                            valid_until=None,
                            source_id=run.source_id,
                            source_updated_at=now,
                            verification_status=FactVerificationStatus.VERIFIED,
                            checked_at=now,
                            created_at=now,
                            updated_at=now,
                            version=1,
                        )
                    )
                    await uow.catalog_inventory.save(
                        InventoryLevel(
                            id=uuid4(),
                            tenant_id=context.tenant.id,
                            variant_id=variant.id,
                            location_code=str(payload["location_code"]).casefold(),
                            available_quantity=int(str(payload["available_quantity"])),
                            reserved_quantity=0,
                            source_id=run.source_id,
                            source_updated_at=now,
                            verification_status=FactVerificationStatus.LIVE,
                            checked_at=now,
                            created_at=now,
                            updated_at=now,
                            version=1,
                        )
                    )
                    if "lead_time_hours" in payload:
                        await uow.catalog_delivery.save(
                            DeliveryFact(
                                id=uuid4(),
                                tenant_id=context.tenant.id,
                                variant_id=variant.id,
                                location_code=str(payload["location_code"]).casefold(),
                                lead_time_hours=int(str(payload["lead_time_hours"])),
                                source_id=run.source_id,
                                source_updated_at=now,
                                verification_status=FactVerificationStatus.VERIFIED,
                                checked_at=now,
                                created_at=now,
                                updated_at=now,
                                version=1,
                            )
                        )
            except Exception:
                failed_run = replace(
                    publishing,
                    status=CatalogImportStatus.FAILED,
                    failed_count=failed + 1,
                    updated_at=now,
                    version=publishing.version + 1,
                )
                await uow.catalog_import_runs.save(failed_run)
                await uow.commit()
                raise

            completed = replace(
                publishing,
                status=CatalogImportStatus.COMPLETED,
                created_count=created,
                updated_count=updated,
                skipped_count=skipped,
                failed_count=failed,
                updated_at=now,
                published_at=now,
                version=publishing.version + 1,
            )
            await uow.catalog_import_runs.save(completed)
            await append_required_audit_event(
                uow.audit_events,
                catalog_import_event(
                    tenant_id=context.tenant.id,
                    run_id=run_id,
                    action=AuditAction.CATALOG_IMPORT_PUBLISHED,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=uuid4(),
                    status=completed.status.value,
                    affected_count=created + updated,
                ),
            )
            await uow.commit()
        return completed

    async def get_commercial_policy(self, *, context: TenantContext) -> CommercialPolicy | None:
        _require_read(context)
        async with self._uow_factory() as uow:
            return await uow.catalog_commercial_policies.get(tenant_id=context.tenant.id)

    async def ensure_default_policies(self, *, context: TenantContext) -> None:
        _require_manage(context)
        now = self._clock.now()
        async with self._uow_factory() as uow:
            if await uow.catalog_freshness_policies.get(tenant_id=context.tenant.id) is None:
                await uow.catalog_freshness_policies.save(
                    CatalogFreshnessPolicy.conservative_defaults(
                        id=uuid4(), tenant_id=context.tenant.id, now=now
                    )
                )
            if await uow.catalog_commercial_policies.get(tenant_id=context.tenant.id) is None:
                await uow.catalog_commercial_policies.save(
                    CommercialPolicy(
                        id=uuid4(),
                        tenant_id=context.tenant.id,
                        allow_discount=False,
                        max_discount_basis_points=0,
                        allow_hold_inventory=False,
                        default_currency="KZT",
                        created_at=now,
                        updated_at=now,
                        version=1,
                    )
                )
            await uow.commit()
