"""Tenant reply suggestion and buyer memory HTTP routes."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from closeros.application.tenant_context import TenantContextUnavailableError
from closeros.domain.access import TenantAccessDeniedError
from closeros.domain.buyer_memory import BuyerMemoryFact
from closeros.domain.identity import Role
from closeros.domain.reply_suggestion import (
    ReplySuggestionAccessDeniedError,
    ReplySuggestionCandidate,
    ReplySuggestionRun,
    confidence_label,
)
from fastapi import APIRouter, Depends, Header, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import apply_security_headers, read_session_cookie
from closeros_api.composition import ApiRuntime
from closeros_api.product_security import (
    ACCESS_DENIED,
    AUTHENTICATION_FAILED,
    REQUEST_UNAVAILABLE,
    audit_context_from_request,
    require_csrf,
    require_origin,
)
from closeros_api.reply_suggestion_schemas import (
    BuyerMemoryFactResponse,
    BuyerMemoryListResponse,
    ConfirmBuyerMemoryRequest,
    CorrectBuyerMemoryRequest,
    GenerateReplySuggestionRequest,
    ReplyCustomerStateResponse,
    ReplyNextBestActionResponse,
    ReplyProductReferenceResponse,
    ReplySelectionResponse,
    ReplySuggestionCandidateResponse,
    ReplySuggestionRunResponse,
    SelectReplyCandidateRequest,
)
from closeros_api.request_correlation import get_request_correlation_id

router = APIRouter(tags=["reply-suggestions"])

_ACCESS_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.MANAGER})


def _runtime(request: Request) -> ApiRuntime:
    runtime = getattr(request.app.state, "auth", None)
    if runtime is None:
        raise RuntimeError("API runtime is not configured")
    return cast(ApiRuntime, runtime)


RuntimeDep = Annotated[ApiRuntime, Depends(_runtime)]


async def _require_context(request: Request, runtime: ApiRuntime, *, tenant_id: UUID) -> object:
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


def _require_access(context: object) -> None:
    from closeros.application.tenant_context import TenantContext

    if not isinstance(context, TenantContext):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)
    if not context.membership.roles.intersection(_ACCESS_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)


def _candidate_response(candidate: ReplySuggestionCandidate) -> ReplySuggestionCandidateResponse:
    return ReplySuggestionCandidateResponse(
        id=candidate.id,
        candidate_key=candidate.candidate_key.value,
        text=candidate.text,
        objective=candidate.objective,
        confidence_basis_points=candidate.confidence_basis_points,
        confidence_label=confidence_label(candidate.confidence_basis_points),
        evidence_message_ids=list(candidate.evidence_message_ids),
        product_references=[
            ReplyProductReferenceResponse(product_id=ref.product_id, variant_id=ref.variant_id)
            for ref in candidate.product_references
        ],
        knowledge_citation_ids=list(candidate.knowledge_citation_ids),
        warnings=list(candidate.warnings),
        is_recommended=candidate.is_recommended,
        created_at=candidate.created_at,
    )


def _run_response(
    run: ReplySuggestionRun, candidates: tuple[ReplySuggestionCandidate, ...]
) -> ReplySuggestionRunResponse:
    customer_state = None
    if run.customer_state is not None:
        customer_state = ReplyCustomerStateResponse(
            intent=run.customer_state.intent.value,
            sales_stage=run.customer_state.sales_stage.value,
            primary_objection=run.customer_state.primary_objection,
            urgency=run.customer_state.urgency.value,
            language=run.customer_state.language,
            missing_information=list(run.customer_state.missing_information),
        )
    next_best_action = None
    if run.next_best_action is not None:
        next_best_action = ReplyNextBestActionResponse(
            action_code=run.next_best_action.action_code.value,
            explanation=run.next_best_action.explanation,
        )
    return ReplySuggestionRunResponse(
        id=run.id,
        conversation_thread_id=run.conversation_thread_id,
        lead_id=run.lead_id,
        status=run.status.value,
        prompt_version=run.prompt_version,
        rubric_version=run.rubric_version,
        provider_code=run.provider_code,
        model_code=run.model_code,
        cost_status=run.cost_status.value,
        failure_code=run.failure_code.value if run.failure_code is not None else None,
        customer_state=customer_state,
        next_best_action=next_best_action,
        escalation_reason=run.escalation_reason,
        created_at=run.created_at,
        updated_at=run.updated_at,
        completed_at=run.completed_at,
        candidates=[_candidate_response(item) for item in candidates],
    )


def _memory_fact_response(fact: BuyerMemoryFact) -> BuyerMemoryFactResponse:
    return BuyerMemoryFactResponse(
        id=fact.id,
        conversation_thread_id=fact.conversation_thread_id,
        lead_id=fact.lead_id,
        fact_type=fact.fact_type.value,
        normalized_value=fact.normalized_value,
        display_value=fact.display_value,
        status=fact.status.value,
        confidence_basis_points=fact.confidence_basis_points,
        confidence_label=confidence_label(fact.confidence_basis_points),
        source_message_id=fact.source_message_id,
        supersedes_fact_id=fact.supersedes_fact_id,
        observed_at=fact.observed_at,
        confirmed_at=fact.confirmed_at,
        expires_at=fact.expires_at,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
        version=fact.version,
    )


def _map_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, ReplySuggestionAccessDeniedError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="request failed")


@router.post(
    "/tenants/{tenant_id}/conversations/{thread_id}/reply-suggestions",
    response_model=ReplySuggestionRunResponse,
)
async def generate_reply_suggestions(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    thread_id: UUID,
    payload: GenerateReplySuggestionRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ReplySuggestionRunResponse:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_access(context)
    if runtime.reply_suggestion_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        from closeros.application.tenant_context import TenantContext

        assert isinstance(context, TenantContext)
        view = await runtime.reply_suggestion_service.generate_suggestions(
            context=context,
            thread_id=thread_id,
            audit_context=audit_context_from_request(request),
            idempotency_key=idempotency_key or payload.idempotency_key,
            catalog=runtime.product_catalog_service,
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    apply_security_headers(response)
    return _run_response(view.run, view.candidates)


@router.get(
    "/tenants/{tenant_id}/conversations/{thread_id}/reply-suggestions/latest",
    response_model=ReplySuggestionRunResponse,
)
async def get_latest_reply_suggestions(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    thread_id: UUID,
) -> ReplySuggestionRunResponse:
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_access(context)
    if runtime.reply_suggestion_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        from closeros.application.tenant_context import TenantContext

        assert isinstance(context, TenantContext)
        view = await runtime.reply_suggestion_service.get_latest(
            context=context,
            thread_id=thread_id,
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    apply_security_headers(response)
    return _run_response(view.run, view.candidates)


@router.post(
    "/tenants/{tenant_id}/reply-suggestions/{run_id}/candidates/{candidate_id}/select",
    response_model=ReplySelectionResponse,
)
async def select_reply_candidate(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    run_id: UUID,
    candidate_id: UUID,
    payload: SelectReplyCandidateRequest,
) -> ReplySelectionResponse:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_access(context)
    if runtime.reply_suggestion_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        from closeros.application.tenant_context import TenantContext

        assert isinstance(context, TenantContext)
        result = await runtime.reply_suggestion_service.select_candidate(
            context=context,
            run_id=run_id,
            candidate_id=candidate_id,
            edited_text=payload.edited_text,
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    apply_security_headers(response)
    return ReplySelectionResponse(
        run_id=result.run.id,
        candidate_id=result.candidate.id,
        outbound_message_id=result.draft.id,
        draft_status=result.draft.status.value,
    )


@router.post("/tenants/{tenant_id}/reply-suggestions/{run_id}/reject")
async def reject_reply_suggestion_run(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    run_id: UUID,
) -> dict[str, str]:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_access(context)
    if runtime.reply_suggestion_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        from closeros.application.tenant_context import TenantContext

        assert isinstance(context, TenantContext)
        await runtime.reply_suggestion_service.reject_run(
            context=context,
            run_id=run_id,
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    apply_security_headers(response)
    return {"status": "rejected"}


@router.get(
    "/tenants/{tenant_id}/conversations/{thread_id}/memory",
    response_model=BuyerMemoryListResponse,
)
async def list_thread_memory(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    thread_id: UUID,
) -> BuyerMemoryListResponse:
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_access(context)
    if runtime.buyer_memory_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        from closeros.application.tenant_context import TenantContext

        assert isinstance(context, TenantContext)
        facts = await runtime.buyer_memory_service.list_effective_for_thread(
            context=context,
            conversation_thread_id=thread_id,
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    apply_security_headers(response)
    return BuyerMemoryListResponse(facts=[_memory_fact_response(fact) for fact in facts])


@router.get(
    "/tenants/{tenant_id}/leads/{lead_id}/memory",
    response_model=BuyerMemoryListResponse,
)
async def list_lead_memory(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    lead_id: UUID,
) -> BuyerMemoryListResponse:
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_access(context)
    if runtime.buyer_memory_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        from closeros.application.tenant_context import TenantContext

        assert isinstance(context, TenantContext)
        facts = await runtime.buyer_memory_service.list_effective_for_lead(
            context=context,
            lead_id=lead_id,
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    apply_security_headers(response)
    return BuyerMemoryListResponse(facts=[_memory_fact_response(fact) for fact in facts])


@router.post(
    "/tenants/{tenant_id}/memory/{fact_id}/confirm",
    response_model=BuyerMemoryFactResponse,
)
async def confirm_buyer_memory_fact(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    fact_id: UUID,
    payload: ConfirmBuyerMemoryRequest,
) -> BuyerMemoryFactResponse:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_access(context)
    if runtime.buyer_memory_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        from closeros.application.tenant_context import TenantContext

        assert isinstance(context, TenantContext)
        fact = await runtime.buyer_memory_service.confirm(
            context=context,
            fact_id=fact_id,
            source_message_id=payload.source_message_id,
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    apply_security_headers(response)
    return _memory_fact_response(fact)


@router.post(
    "/tenants/{tenant_id}/memory/{fact_id}/correct",
    response_model=BuyerMemoryFactResponse,
)
async def correct_buyer_memory_fact(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    fact_id: UUID,
    payload: CorrectBuyerMemoryRequest,
) -> BuyerMemoryFactResponse:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_access(context)
    if runtime.buyer_memory_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        from closeros.application.tenant_context import TenantContext

        assert isinstance(context, TenantContext)
        fact = await runtime.buyer_memory_service.correct(
            context=context,
            fact_id=fact_id,
            normalized_value=payload.normalized_value,
            display_value=payload.display_value,
            source_message_id=payload.source_message_id,
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    apply_security_headers(response)
    return _memory_fact_response(fact)


@router.post(
    "/tenants/{tenant_id}/memory/{fact_id}/reject",
    response_model=BuyerMemoryFactResponse,
)
async def reject_buyer_memory_fact(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    fact_id: UUID,
) -> BuyerMemoryFactResponse:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_access(context)
    if runtime.buyer_memory_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        from closeros.application.tenant_context import TenantContext

        assert isinstance(context, TenantContext)
        fact = await runtime.buyer_memory_service.reject(
            context=context,
            fact_id=fact_id,
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    apply_security_headers(response)
    return _memory_fact_response(fact)


@router.delete("/tenants/{tenant_id}/memory/{fact_id}")
async def delete_buyer_memory_fact(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    fact_id: UUID,
) -> dict[str, str]:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_access(context)
    if runtime.buyer_memory_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        from closeros.application.tenant_context import TenantContext

        assert isinstance(context, TenantContext)
        await runtime.buyer_memory_service.soft_delete(
            context=context,
            fact_id=fact_id,
            audit_context=audit_context_from_request(request),
        )
    except Exception as exc:
        raise _map_errors(exc) from exc
    apply_security_headers(response)
    return {"status": "deleted"}
