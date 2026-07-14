"""Tenant product catalog HTTP routes (owner/sales_head write; broader read)."""

from __future__ import annotations

from typing import Annotated, Any, cast
from uuid import UUID

from closeros.application.product_catalog_grounding import AiCatalogClaim, validate_catalog_claim
from closeros.application.product_catalog_tools import CatalogToolExecutor, parse_tool_request
from closeros.application.tenant_context import TenantContext, TenantContextUnavailableError
from closeros.domain.access import TenantAccessDeniedError
from closeros.domain.identity import Role
from closeros.domain.product_catalog import (
    CatalogAuthorizationError,
    CatalogDomainError,
    CatalogEntityStatus,
    CatalogGroundingError,
    CatalogOptimisticLockError,
    CatalogSearchFilters,
    CommercialActionCode,
    FactVerificationStatus,
    PriceKind,
    Product,
    ProductVariant,
)
from fastapi import APIRouter, Depends, Query, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import apply_security_headers, read_session_cookie
from closeros_api.composition import ApiRuntime
from closeros_api.product_catalog_schemas import (
    CatalogGroundClaimRequest,
    CatalogGroundClaimResponse,
    CatalogImportRunResponse,
    CatalogImportUploadRequest,
    CatalogInventorySetRequest,
    CatalogPriceSetRequest,
    CatalogProductCreateRequest,
    CatalogProductDetailResponse,
    CatalogProductListResponse,
    CatalogProductResponse,
    CatalogProductUpdateRequest,
    CatalogPublishRequest,
    CatalogSearchHitResponse,
    CatalogSearchResponse,
    CatalogStatusChangeRequest,
    CatalogToolExecuteRequest,
    CatalogToolExecuteResponse,
    CatalogVariantCreateRequest,
    CatalogVariantResponse,
)
from closeros_api.product_security import (
    audit_context_from_request,
    require_csrf,
    require_origin,
)
from closeros_api.request_correlation import get_request_correlation_id

router = APIRouter(tags=["catalog"])

AUTHENTICATION_FAILED = "authentication failed"
ACCESS_DENIED = "access denied"
_READ_ROLES = frozenset(
    {Role.OWNER, Role.SALES_HEAD, Role.MANAGER, Role.ANALYST, Role.COMPLIANCE_ADMIN}
)
_WRITE_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD})


def _runtime(request: Request) -> ApiRuntime:
    runtime = getattr(request.app.state, "auth", None)
    if runtime is None:
        raise RuntimeError("API runtime is not configured")
    return cast(ApiRuntime, runtime)


RuntimeDep = Annotated[ApiRuntime, Depends(_runtime)]


async def _require_context(
    request: Request, runtime: ApiRuntime, *, tenant_id: UUID
) -> TenantContext:
    token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    try:
        return await runtime.tenant_context_resolver.resolve(
            raw_token=token,
            tenant_id=tenant_id,
            correlation_id=get_request_correlation_id(request),
            now=runtime.clock.now(),
        )
    except TenantContextUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED
        ) from None
    except TenantAccessDeniedError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from None


def _require_read(context: TenantContext) -> None:
    if not context.membership.roles.intersection(_READ_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)


def _require_write(context: TenantContext) -> None:
    if not context.membership.roles.intersection(_WRITE_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)


def _map_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, CatalogAuthorizationError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)
    if isinstance(exc, CatalogOptimisticLockError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="version conflict")
    if isinstance(exc, (CatalogDomainError, CatalogGroundingError, ValueError)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="request failed")


def _product_response(product: Product) -> CatalogProductResponse:
    return CatalogProductResponse(
        id=product.id,
        sku=product.sku,
        name=product.name,
        category_code=product.category_code,
        description=product.description,
        status=product.status.value,
        version=product.version,
        updated_at=product.updated_at,
    )


def _variant_response(variant: ProductVariant) -> CatalogVariantResponse:
    return CatalogVariantResponse(
        id=variant.id,
        product_id=variant.product_id,
        sku=variant.sku,
        display_name=variant.display_name,
        attributes=dict(variant.attributes),
        status=variant.status.value,
        version=variant.version,
    )


def _catalog_service(runtime: ApiRuntime) -> Any:
    service = runtime.product_catalog_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="catalog unavailable"
        )
    return service


@router.get("/tenants/{tenant_id}/catalog/products", response_model=CatalogProductListResponse)
async def list_products(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    category_code: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = None,
) -> CatalogProductListResponse:
    apply_security_headers(response)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_read(context)
    try:
        items = await _catalog_service(runtime).list_products(
            context=context,
            category_code=category_code,
            status=status_filter,
            query_text=q,
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return CatalogProductListResponse(items=[_product_response(item) for item in items])


@router.post(
    "/tenants/{tenant_id}/catalog/products",
    response_model=CatalogProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    body: CatalogProductCreateRequest,
) -> CatalogProductResponse:
    apply_security_headers(response)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_write(context)
    try:
        product = await _catalog_service(runtime).create_product_draft(
            context=context,
            sku=body.sku,
            name=body.name,
            category_code=body.category_code,
            description=body.description,
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return _product_response(product)


@router.get(
    "/tenants/{tenant_id}/catalog/products/{product_id}",
    response_model=CatalogProductDetailResponse,
)
async def get_product(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    product_id: UUID,
) -> CatalogProductDetailResponse:
    apply_security_headers(response)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_read(context)
    try:
        detail = await _catalog_service(runtime).get_product_details(
            context=context, product_id=product_id
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return CatalogProductDetailResponse(
        product=_product_response(detail["product"]),
        variants=[_variant_response(item) for item in detail["variants"]],
    )


@router.patch(
    "/tenants/{tenant_id}/catalog/products/{product_id}",
    response_model=CatalogProductResponse,
)
async def update_product(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    product_id: UUID,
    body: CatalogProductUpdateRequest,
) -> CatalogProductResponse:
    apply_security_headers(response)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_write(context)
    try:
        product = await _catalog_service(runtime).update_product(
            context=context,
            product_id=product_id,
            expected_version=body.expected_version,
            name=body.name,
            category_code=body.category_code,
            description=body.description,
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return _product_response(product)


@router.post(
    "/tenants/{tenant_id}/catalog/products/{product_id}/publish",
    response_model=CatalogProductResponse,
)
async def publish_product(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    product_id: UUID,
    body: CatalogPublishRequest,
) -> CatalogProductResponse:
    apply_security_headers(response)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_write(context)
    try:
        product = await _catalog_service(runtime).publish_product(
            context=context,
            product_id=product_id,
            expected_version=body.expected_version,
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return _product_response(product)


@router.post(
    "/tenants/{tenant_id}/catalog/products/{product_id}/status",
    response_model=CatalogProductResponse,
)
async def change_status(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    product_id: UUID,
    body: CatalogStatusChangeRequest,
) -> CatalogProductResponse:
    apply_security_headers(response)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_write(context)
    try:
        product = await _catalog_service(runtime).deactivate_or_archive(
            context=context,
            product_id=product_id,
            expected_version=body.expected_version,
            status=CatalogEntityStatus(body.status),
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return _product_response(product)


@router.post(
    "/tenants/{tenant_id}/catalog/products/{product_id}/variants",
    response_model=CatalogVariantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_variant(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    product_id: UUID,
    body: CatalogVariantCreateRequest,
) -> CatalogVariantResponse:
    apply_security_headers(response)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_write(context)
    try:
        variant = await _catalog_service(runtime).add_variant(
            context=context,
            product_id=product_id,
            sku=body.sku,
            display_name=body.display_name,
            attributes=body.attributes,
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return _variant_response(variant)


@router.post("/tenants/{tenant_id}/catalog/variants/{variant_id}/price")
async def set_price(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    variant_id: UUID,
    body: CatalogPriceSetRequest,
) -> dict[str, Any]:
    apply_security_headers(response)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_write(context)
    try:
        price = await _catalog_service(runtime).set_price(
            context=context,
            variant_id=variant_id,
            amount_minor=body.amount_minor,
            currency=body.currency,
            price_kind=PriceKind(body.price_kind),
            verification_status=FactVerificationStatus(body.verification_status),
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return {
        "id": str(price.id),
        "amount_minor": price.amount_minor,
        "currency": price.currency,
        "verification_status": price.verification_status.value,
    }


@router.post("/tenants/{tenant_id}/catalog/variants/{variant_id}/inventory")
async def set_inventory(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    variant_id: UUID,
    body: CatalogInventorySetRequest,
) -> dict[str, Any]:
    apply_security_headers(response)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_write(context)
    try:
        level = await _catalog_service(runtime).set_inventory(
            context=context,
            variant_id=variant_id,
            location_code=body.location_code,
            available_quantity=body.available_quantity,
            reserved_quantity=body.reserved_quantity,
            verification_status=FactVerificationStatus(body.verification_status),
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return {
        "id": str(level.id),
        "location_code": level.location_code,
        "available_quantity": level.available_quantity,
        "verification_status": level.verification_status.value,
    }


@router.get("/tenants/{tenant_id}/catalog/search", response_model=CatalogSearchResponse)
async def search_catalog(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    category: str | None = None,
    currency: str | None = None,
    location: str | None = None,
    color: str | None = None,
    material: str | None = None,
    budget_max_minor: int | None = None,
    in_stock_only: bool = False,
    q: str | None = None,
    limit: int = 10,
) -> CatalogSearchResponse:
    apply_security_headers(response)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_read(context)
    try:
        hits = await _catalog_service(runtime).search_products(
            context=context,
            filters=CatalogSearchFilters(
                category=category,
                currency=currency,
                location=location,
                color=color,
                material=material,
                budget_max_minor=budget_max_minor,
                in_stock_only=in_stock_only,
                query_text=q,
                limit=limit,
            ),
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return CatalogSearchResponse(
        items=[
            CatalogSearchHitResponse(
                product_id=hit.product_id,
                variant_id=hit.variant_id,
                product_sku=hit.product_sku,
                variant_sku=hit.variant_sku,
                product_name=hit.product_name,
                variant_display_name=hit.variant_display_name,
                category_code=hit.category_code,
                amount_minor=hit.amount_minor,
                currency=hit.currency,
                available_quantity=hit.available_quantity,
                in_stock=hit.in_stock,
                price_usable=hit.price_provenance.usable,
                inventory_usable=hit.inventory_provenance.usable,
                delivery_usable=hit.delivery_usable,
                attributes=dict(hit.attributes),
            )
            for hit in hits
        ]
    )


@router.post(
    "/tenants/{tenant_id}/catalog/imports",
    response_model=CatalogImportRunResponse,
)
async def upload_import(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    body: CatalogImportUploadRequest,
) -> CatalogImportRunResponse:
    apply_security_headers(response)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_write(context)
    try:
        result = await _catalog_service(runtime).upload_csv_import(
            context=context,
            payload=body.csv_text.encode("utf-8"),
            delimiter=body.delimiter,
            mapping=body.mapping,
            audit_context=audit_context_from_request(request),
            dry_run=body.dry_run,
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    if isinstance(result, dict) and result.get("dry_run"):
        return CatalogImportRunResponse(
            id=None,
            status=str(result["status"]),
            total_rows=int(result["total_rows"]),
            valid_rows=int(result["valid_rows"]),
            invalid_rows=int(result["invalid_rows"]),
            dry_run=True,
            rows=[
                {
                    "row_number": row.row_number,
                    "is_valid": row.is_valid,
                    "error_code": row.error_code.value if row.error_code else None,
                }
                for row in result["rows"]
            ],
        )
    return CatalogImportRunResponse(
        id=result.id,
        status=result.status.value,
        total_rows=result.total_rows,
        valid_rows=result.valid_rows,
        invalid_rows=result.invalid_rows,
        created_count=result.created_count,
        updated_count=result.updated_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
    )


@router.post(
    "/tenants/{tenant_id}/catalog/imports/{run_id}/publish",
    response_model=CatalogImportRunResponse,
)
async def publish_import(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    run_id: UUID,
) -> CatalogImportRunResponse:
    apply_security_headers(response)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_write(context)
    try:
        result = await _catalog_service(runtime).publish_csv_import(
            context=context,
            run_id=run_id,
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return CatalogImportRunResponse(
        id=result.id,
        status=result.status.value,
        total_rows=result.total_rows,
        valid_rows=result.valid_rows,
        invalid_rows=result.invalid_rows,
        created_count=result.created_count,
        updated_count=result.updated_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
    )


@router.post(
    "/tenants/{tenant_id}/catalog/tools/execute",
    response_model=CatalogToolExecuteResponse,
)
async def execute_catalog_tool(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    body: CatalogToolExecuteRequest,
) -> CatalogToolExecuteResponse:
    apply_security_headers(response)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_read(context)
    try:
        tool_request = parse_tool_request({"tool": body.tool, "arguments": body.arguments})
        result = await CatalogToolExecutor(_catalog_service(runtime)).execute(
            context=context,
            request=tool_request,
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return CatalogToolExecuteResponse(
        tool=result.tool,
        results=list(result.results),
        warnings=list(result.warnings),
    )


@router.post(
    "/tenants/{tenant_id}/catalog/grounding/validate",
    response_model=CatalogGroundClaimResponse,
)
async def validate_grounding(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    body: CatalogGroundClaimRequest,
) -> CatalogGroundClaimResponse:
    apply_security_headers(response)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_read(context)
    service = _catalog_service(runtime)
    try:
        detail = await service.get_product_details(context=context, product_id=body.product_id)
        product = detail["product"]
        hits = await service.search_products(
            context=context,
            filters=CatalogSearchFilters(limit=25),
        )
        hit = next((item for item in hits if item.variant_id == body.variant_id), None)
        if body.tool_result_product_ids:
            tool_hits = [
                item for item in hits if item.product_id in set(body.tool_result_product_ids)
            ]
        else:
            tool_hits = list(hits)
        policy = await service.get_commercial_policy(context=context)
        claim = AiCatalogClaim(
            product_id=body.product_id,
            variant_id=body.variant_id,
            claimed_amount_minor=body.claimed_amount_minor,
            claimed_currency=body.claimed_currency,
            claimed_in_stock=body.claimed_in_stock,
            claimed_discount_basis_points=body.claimed_discount_basis_points,
            commercial_action=(
                CommercialActionCode(body.commercial_action) if body.commercial_action else None
            ),
            reply_text=body.reply_text,
            product_name_in_text=body.product_name_in_text,
        )
        result = validate_catalog_claim(
            tenant_id=tenant_id,
            claim=claim,
            product=product,
            hit=hit,
            tool_hits=tool_hits,
            policy=policy,
            now=runtime.clock.now(),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    return CatalogGroundClaimResponse(
        accepted=result.accepted,
        reason_code=result.reason_code,
        safe_fallback_text=result.safe_fallback_text,
        rendered_price_fragment=result.rendered_price_fragment,
        rendered_stock_fragment=result.rendered_stock_fragment,
    )
