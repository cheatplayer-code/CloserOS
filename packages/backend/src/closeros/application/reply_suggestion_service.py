"""Application service for grounded reply suggestion generation and selection."""

from __future__ import annotations

import difflib
import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

from sqlalchemy import select

from closeros.application.ai_policy_persistence import TenantAiPolicyRecord
from closeros.application.ai_ports import (
    AiCredentialResolver,
    AiProvider,
    ProviderRequest,
    ProviderResult,
)
from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.buyer_memory_inference import infer_memory_facts_from_customer_state
from closeros.application.clock import Clock, SystemClock
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.outbound_message_service import OutboundMessageService
from closeros.application.product_catalog_service import ProductCatalogService
from closeros.application.reply_suggestion_audit import (
    reply_suggestion_blocked_event,
    reply_suggestion_completed_event,
    reply_suggestion_rejected_event,
    reply_suggestion_requested_event,
    reply_suggestion_selected_event,
)
from closeros.application.reply_suggestion_context import (
    ReplyContextTooLargeError,
    assemble_reply_context,
)
from closeros.application.reply_suggestion_grounding import enrich_validated_candidates
from closeros.application.reply_suggestion_prompt import build_reply_suggestion_prompt
from closeros.application.reply_suggestion_validator import (
    ReplyOutputValidationError,
    validate_reply_suggestion_json,
)
from closeros.application.tenant_context import TenantContext
from closeros.domain.ai_analysis import AiFailureCode, AiProviderCode, AiPurpose
from closeros.domain.audit import AuditActorType
from closeros.domain.buyer_memory import BuyerMemoryFact, select_effective_memory_facts
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    EncryptedContentKind,
)
from closeros.domain.identity import Role
from closeros.domain.outbound_message import OutboundMessage, OutboundMessageKind
from closeros.domain.privacy_redaction import SANITIZATION_POLICY_VERSION
from closeros.domain.product_catalog import CatalogSearchFilters, CatalogSearchHit
from closeros.domain.reply_suggestion import (
    MAX_EDIT_DISTANCE_BASIS_POINTS,
    REPLY_PROMPT_VERSION,
    REPLY_RUBRIC_VERSION,
    ReplyCandidateKey,
    ReplyCostStatus,
    ReplyFailureCode,
    ReplyProductReference,
    ReplySuggestionAccessDeniedError,
    ReplySuggestionCandidate,
    ReplySuggestionError,
    ReplySuggestionEvent,
    ReplySuggestionEventType,
    ReplySuggestionRun,
    ReplySuggestionStatus,
)
from closeros.infrastructure.canonical_orm import ManagerAssignmentRow, MessageRow
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]

_ACCESS_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.MANAGER})
_PRIVILEGED_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD})
_DEFAULT_MODEL = "synthetic-reply-v1"


class ReplySuggestionServiceError(ReplySuggestionError):
    """Raised when reply suggestion operations cannot be completed."""


class ReplySuggestionInputTooLargeError(ReplySuggestionServiceError):
    """Raised when conversation context exceeds configured prompt bounds."""


class ReplySuggestionSanitizationMissingError(ReplySuggestionServiceError):
    """Raised when sanitized transcript content is unavailable."""


@dataclass(frozen=True, slots=True)
class ReplySuggestionView:
    run: ReplySuggestionRun
    candidates: tuple[ReplySuggestionCandidate, ...]


@dataclass(frozen=True, slots=True)
class ReplySelectionResult:
    run: ReplySuggestionRun
    candidate: ReplySuggestionCandidate
    draft: OutboundMessage


def _is_manager_only(roles: frozenset[Role]) -> bool:
    return Role.MANAGER in roles and not roles.intersection(_PRIVILEGED_ROLES)


def _require_access(context: TenantContext) -> None:
    if not context.membership.roles.intersection(_ACCESS_ROLES):
        raise ReplySuggestionAccessDeniedError("access denied")


def _edit_basis_points(original: str, edited: str) -> int:
    if original == edited:
        return 0
    ratio = difflib.SequenceMatcher(a=original, b=edited).ratio()
    return min(MAX_EDIT_DISTANCE_BASIS_POINTS, int((1.0 - ratio) * 10_000))


def _latency_bucket(milliseconds: int | None) -> str:
    if milliseconds is None:
        return "unknown"
    if milliseconds < 1_000:
        return "lt_1s"
    if milliseconds < 5_000:
        return "lt_5s"
    return "gte_5s"


def _map_ai_failure(code: AiFailureCode) -> ReplyFailureCode:
    mapping = {
        AiFailureCode.POLICY_DISABLED: ReplyFailureCode.POLICY_DISABLED,
        AiFailureCode.PURPOSE_NOT_ALLOWED: ReplyFailureCode.PURPOSE_NOT_ALLOWED,
        AiFailureCode.BUDGET_EXCEEDED: ReplyFailureCode.BUDGET_EXCEEDED,
        AiFailureCode.SANITIZATION_MISSING: ReplyFailureCode.SANITIZATION_MISSING,
        AiFailureCode.INPUT_TOO_LARGE: ReplyFailureCode.INPUT_TOO_LARGE,
        AiFailureCode.PROVIDER_UNAVAILABLE: ReplyFailureCode.PROVIDER_FAILURE,
        AiFailureCode.PROVIDER_OUTPUT_INVALID: ReplyFailureCode.OUTPUT_INVALID,
        AiFailureCode.UNSAFE_OUTPUT: ReplyFailureCode.OUTPUT_INVALID,
    }
    return mapping.get(code, ReplyFailureCode.PROVIDER_FAILURE)


def _provider_storage_code(provider_code: AiProviderCode) -> str:
    if provider_code is AiProviderCode.OPENAI_COMPATIBLE:
        return "openai"
    return "local"


def _apply_provider_result_metadata(
    *,
    run: ReplySuggestionRun,
    provider_result: ProviderResult,
) -> ReplySuggestionRun:
    usage = provider_result.usage
    cost_status = ReplyCostStatus.UNKNOWN
    estimated_cost_microunits: int | None = None
    if provider_result.provider_code is AiProviderCode.SYNTHETIC:
        cost_status = ReplyCostStatus.NOT_APPLICABLE
    elif usage is not None and usage.estimated_cost_microunits > 0:
        cost_status = ReplyCostStatus.KNOWN
        estimated_cost_microunits = usage.estimated_cost_microunits

    return replace(
        run,
        provider_code=_provider_storage_code(provider_result.provider_code),
        model_code=provider_result.model_code,
        input_tokens=None if usage is None else usage.input_tokens,
        output_tokens=None if usage is None else usage.output_tokens,
        latency_milliseconds=None if usage is None else usage.latency_milliseconds,
        cost_status=cost_status,
        estimated_cost_microunits=estimated_cost_microunits,
    )


class ReplySuggestionService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        content_encryption: ContentEncryptionService,
        outbound_message_service: OutboundMessageService,
        clock: Clock | None = None,
        ai_provider: AiProvider | None = None,
        ai_credential_resolver: AiCredentialResolver | None = None,
        model_code: str | None = _DEFAULT_MODEL,
        uuid_factory: _UuidFactory | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._content_encryption = content_encryption
        self._outbound_message_service = outbound_message_service
        self._clock = clock or SystemClock()
        self._ai_provider = ai_provider
        self._ai_credential_resolver = ai_credential_resolver
        normalized_model_code: str | None = None
        if model_code is not None:
            normalized_model_code = model_code.strip()
            if not normalized_model_code:
                raise ValueError("model_code must be non-empty when configured")
        self._model_code = normalized_model_code
        self._uuid_factory = uuid_factory or uuid4

    async def generate_suggestions(
        self,
        *,
        context: TenantContext,
        thread_id: UUID,
        audit_context: AuditContext,
        idempotency_key: str | None = None,
        catalog: ProductCatalogService | None = None,
    ) -> ReplySuggestionView:
        _require_access(context)
        now = self._clock.now()
        tenant_id = context.tenant.id
        run_id = self._uuid_factory()

        async with self._uow_factory() as uow:
            if idempotency_key is not None:
                existing = await uow.reply_suggestion_runs.get_by_idempotency(
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                )
                if existing is not None:
                    candidates = await uow.reply_suggestion_candidates.list_for_run(
                        tenant_id=tenant_id,
                        run_id=existing.id,
                    )
                    return ReplySuggestionView(run=existing, candidates=tuple(candidates))

            thread = await uow.conversation_threads.get_by_id(
                tenant_id=tenant_id,
                thread_id=thread_id,
            )
            if thread is None:
                raise ReplySuggestionServiceError("conversation unavailable")
            await self._assert_thread_access(
                uow=uow,
                tenant_id=tenant_id,
                thread_id=thread_id,
                roles=context.membership.roles,
                user_id=context.user.id,
            )

            provider_code: AiProviderCode | None = None
            if self._ai_provider is not None:
                provider_code = self._ai_provider.provider_code
            model_code = self._model_code

            run = ReplySuggestionRun(
                id=run_id,
                tenant_id=tenant_id,
                conversation_thread_id=thread_id,
                lead_id=None,
                requested_by_user_id=context.user.id,
                status=ReplySuggestionStatus.RUNNING,
                prompt_version=REPLY_PROMPT_VERSION,
                rubric_version=REPLY_RUBRIC_VERSION,
                provider_code=(
                    None if provider_code is None else _provider_storage_code(provider_code)
                ),
                model_code=model_code,
                input_tokens=None,
                output_tokens=None,
                latency_milliseconds=None,
                provider_request_id=None,
                cost_status=ReplyCostStatus.UNKNOWN,
                estimated_cost_microunits=None,
                failure_code=None,
                customer_state=None,
                next_best_action=None,
                escalation_reason=None,
                idempotency_key=idempotency_key,
                input_digest=None,
                output_digest=None,
                created_at=now,
                updated_at=now,
                completed_at=None,
                version=1,
            )
            await uow.reply_suggestion_runs.save(run)
            await uow.reply_suggestion_events.append(
                ReplySuggestionEvent(
                    id=self._uuid_factory(),
                    tenant_id=tenant_id,
                    run_id=run_id,
                    event_type=ReplySuggestionEventType.REQUESTED,
                    actor_user_id=context.user.id,
                    candidate_id=None,
                    outbound_message_id=None,
                    metadata={},
                    occurred_at=now,
                )
            )
            await append_required_audit_event(
                uow.audit_events,
                reply_suggestion_requested_event(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    provider_code=run.provider_code or "unknown",
                    purpose_code=AiPurpose.REPLY_SUGGESTION.value,
                    prompt_version=REPLY_PROMPT_VERSION,
                    rubric_version=REPLY_RUBRIC_VERSION,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()

        policy_record = await self._load_ai_policy(tenant_id=tenant_id)
        if policy_record is None or policy_record.mode == "off":
            return await self._finalize_blocked(
                tenant_id=tenant_id,
                run_id=run_id,
                failure_code=ReplyFailureCode.POLICY_DISABLED,
                audit_context=audit_context,
                actor_id=context.user.id,
            )

        if self._ai_provider is None or provider_code is None or model_code is None:
            return await self._finalize_blocked(
                tenant_id=tenant_id,
                run_id=run_id,
                failure_code=ReplyFailureCode.PROVIDER_FAILURE,
                audit_context=audit_context,
                actor_id=context.user.id,
            )

        try:
            sanitized_messages, evidence_ids, context_summary = await self._load_sanitized_messages(
                tenant_id=tenant_id,
                thread_id=thread_id,
                audit_context=audit_context,
                actor_id=context.user.id,
            )
        except ReplySuggestionInputTooLargeError:
            return await self._finalize_blocked(
                tenant_id=tenant_id,
                run_id=run_id,
                failure_code=ReplyFailureCode.INPUT_TOO_LARGE,
                audit_context=audit_context,
                actor_id=context.user.id,
            )
        except ReplySuggestionSanitizationMissingError:
            return await self._finalize_blocked(
                tenant_id=tenant_id,
                run_id=run_id,
                failure_code=ReplyFailureCode.SANITIZATION_MISSING,
                audit_context=audit_context,
                actor_id=context.user.id,
            )

        if not sanitized_messages:
            return await self._finalize_blocked(
                tenant_id=tenant_id,
                run_id=run_id,
                failure_code=ReplyFailureCode.SANITIZATION_MISSING,
                audit_context=audit_context,
                actor_id=context.user.id,
            )

        memory_facts: tuple[BuyerMemoryFact, ...] = ()
        async with self._uow_factory() as uow:
            raw_facts = await uow.buyer_memory_facts.list_for_thread(
                tenant_id=tenant_id,
                conversation_thread_id=thread_id,
            )
            memory_facts = select_effective_memory_facts(raw_facts, now=now)

        product_hits: Sequence[CatalogSearchHit] = ()
        allowed_actions: list[str] = []
        if catalog is not None:
            product_hits = await catalog.search_products(
                context=context,
                filters=CatalogSearchFilters(query_text=None, limit=8),
                audit_context=None,
            )
            commercial = await catalog.get_allowed_commercial_actions(context=context)
            allowed_actions = [action.value for action in commercial]

        prompt_bundle = build_reply_suggestion_prompt(
            sanitized_messages=sanitized_messages,
            memory_facts=memory_facts,
            product_hits=product_hits,
            allowed_commercial_actions=allowed_actions,
            playbook_snippets=(),
            structured_summary=context_summary,
        )
        prompt_text = f"{prompt_bundle.system_prompt}\n\n{prompt_bundle.user_prompt}"
        input_digest = hashlib.sha256(prompt_text.encode("utf-8")).digest()
        allowed_products: frozenset[tuple[UUID, UUID]] = frozenset(
            (hit.product_id, hit.variant_id) for hit in product_hits
        )

        bearer_key = ""
        if self._ai_credential_resolver is not None:
            resolved = await self._ai_credential_resolver.resolve_bearer_key(
                tenant_id=tenant_id,
                provider_code=provider_code,
            )
            bearer_key = resolved or ""

        provider_request = ProviderRequest(
            tenant_id=tenant_id,
            provider_code=provider_code,
            purpose=AiPurpose.REPLY_SUGGESTION,
            model_code=model_code,
            prompt_version=REPLY_PROMPT_VERSION,
            rubric_version=REPLY_RUBRIC_VERSION,
            prompt_text=prompt_text,
            evidence_message_ids=evidence_ids,
            input_digest=input_digest,
            requested_at=now,
        )

        try:
            provider_result = await self._ai_provider.call_chat_json(
                request=provider_request,
                bearer_key=bearer_key,
            )
        except Exception:
            return await self._finalize_failed(
                tenant_id=tenant_id,
                run_id=run_id,
                failure_code=ReplyFailureCode.PROVIDER_FAILURE,
                input_digest=input_digest,
                audit_context=audit_context,
                actor_id=context.user.id,
            )

        if (
            provider_result.provider_code is not provider_code
            or provider_result.purpose is not AiPurpose.REPLY_SUGGESTION
        ):
            return await self._finalize_failed(
                tenant_id=tenant_id,
                run_id=run_id,
                failure_code=ReplyFailureCode.OUTPUT_INVALID,
                input_digest=input_digest,
                audit_context=audit_context,
                actor_id=context.user.id,
            )

        try:
            validated = validate_reply_suggestion_json(
                raw_text=provider_result.output_text,
                allowed_evidence_message_ids=frozenset(evidence_ids),
                allowed_product_variant_ids=allowed_products,
                allowed_knowledge_chunk_ids=frozenset(),
            )
        except ReplyOutputValidationError as error:
            failure = _map_ai_failure(error.failure_code)
            return await self._finalize_failed(
                tenant_id=tenant_id,
                run_id=run_id,
                failure_code=failure,
                input_digest=input_digest,
                audit_context=audit_context,
                actor_id=context.user.id,
            )

        recommended, alternatives = enrich_validated_candidates(
            recommended=validated.recommended,
            alternatives=validated.alternatives,
            product_hits=product_hits,
        )
        validated = replace(
            validated,
            recommended=recommended,
            alternatives=alternatives,
        )

        completed_at = self._clock.now()
        candidates = self._build_candidates(
            tenant_id=tenant_id,
            run_id=run_id,
            validated=validated,
            created_at=completed_at,
        )

        usage = provider_result.usage
        token_count = 0
        if usage is not None:
            token_count = usage.input_tokens + usage.output_tokens

        inferred_memory = infer_memory_facts_from_customer_state(
            tenant_id=tenant_id,
            conversation_thread_id=thread_id,
            lead_id=None,
            customer_state=validated.customer_state,
            source_message_id=evidence_ids[-1] if evidence_ids else None,
            source_analysis_id=None,
            now=completed_at,
            uuid_factory=self._uuid_factory,
        )
        effective_by_type = {fact.fact_type: fact for fact in memory_facts}
        memory_to_persist: list[BuyerMemoryFact] = []
        for fact in inferred_memory:
            existing_memory_fact = effective_by_type.get(fact.fact_type)
            if (
                existing_memory_fact is not None
                and existing_memory_fact.normalized_value == fact.normalized_value
            ):
                continue
            if existing_memory_fact is not None:
                fact = replace(
                    fact,
                    supersedes_fact_id=existing_memory_fact.id,
                )
            memory_to_persist.append(fact)

        async with self._uow_factory() as uow:
            current_run = await uow.reply_suggestion_runs.get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            if current_run is None:
                raise ReplySuggestionServiceError("run unavailable")
            completed_run = replace(
                current_run,
                status=ReplySuggestionStatus.COMPLETED,
                customer_state=validated.customer_state,
                next_best_action=validated.next_best_action,
                escalation_reason=validated.escalation,
                input_digest=input_digest,
                output_digest=validated.output_digest,
                updated_at=completed_at,
                completed_at=completed_at,
            )
            completed_run = _apply_provider_result_metadata(
                run=completed_run,
                provider_result=provider_result,
            )
            await uow.reply_suggestion_runs.save(completed_run)
            await uow.reply_suggestion_candidates.replace_for_run(
                tenant_id=tenant_id,
                run_id=run_id,
                candidates=candidates,
            )
            for fact in memory_to_persist:
                await uow.buyer_memory_facts.save(fact)
            await uow.reply_suggestion_events.append(
                ReplySuggestionEvent(
                    id=self._uuid_factory(),
                    tenant_id=tenant_id,
                    run_id=run_id,
                    event_type=ReplySuggestionEventType.GENERATED,
                    actor_user_id=None,
                    candidate_id=None,
                    outbound_message_id=None,
                    metadata={"candidate_count": len(candidates)},
                    occurred_at=completed_at,
                )
            )
            await append_required_audit_event(
                uow.audit_events,
                reply_suggestion_completed_event(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    candidate_count=len(candidates),
                    token_count=token_count,
                    latency_bucket=_latency_bucket(
                        None if usage is None else usage.latency_milliseconds
                    ),
                    provider_code=completed_run.provider_code or "unknown",
                    purpose_code=AiPurpose.REPLY_SUGGESTION.value,
                    rubric_version=REPLY_RUBRIC_VERSION,
                    occurred_at=completed_at,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()

        return ReplySuggestionView(run=completed_run, candidates=candidates)

    async def get_latest(
        self,
        *,
        context: TenantContext,
        thread_id: UUID,
    ) -> ReplySuggestionView | None:
        _require_access(context)
        tenant_id = context.tenant.id
        async with self._uow_factory() as uow:
            await self._assert_thread_access(
                uow=uow,
                tenant_id=tenant_id,
                thread_id=thread_id,
                roles=context.membership.roles,
                user_id=context.user.id,
            )
            run = await uow.reply_suggestion_runs.latest_for_thread(
                tenant_id=tenant_id,
                conversation_thread_id=thread_id,
            )
            if run is None:
                return None
            candidates = await uow.reply_suggestion_candidates.list_for_run(
                tenant_id=tenant_id,
                run_id=run.id,
            )
        return ReplySuggestionView(run=run, candidates=tuple(candidates))

    async def select_candidate(
        self,
        *,
        context: TenantContext,
        run_id: UUID,
        candidate_id: UUID,
        audit_context: AuditContext,
        edited_text: str | None = None,
    ) -> ReplySelectionResult:
        _require_access(context)
        tenant_id = context.tenant.id
        now = self._clock.now()

        async with self._uow_factory() as uow:
            run = await uow.reply_suggestion_runs.get(tenant_id=tenant_id, run_id=run_id)
            if run is None:
                raise ReplySuggestionServiceError("run unavailable")
            await self._assert_thread_access(
                uow=uow,
                tenant_id=tenant_id,
                thread_id=run.conversation_thread_id,
                roles=context.membership.roles,
                user_id=context.user.id,
            )
            candidate = await uow.reply_suggestion_candidates.get(
                tenant_id=tenant_id,
                candidate_id=candidate_id,
            )
            if candidate is None or candidate.run_id != run_id:
                raise ReplySuggestionServiceError("candidate unavailable")
            thread = await uow.conversation_threads.get_by_id(
                tenant_id=tenant_id,
                thread_id=run.conversation_thread_id,
            )
            if thread is None:
                raise ReplySuggestionServiceError("conversation unavailable")

        final_text = candidate.text if edited_text is None else edited_text.strip()
        if not final_text:
            raise ReplySuggestionServiceError("reply text required")
        edit_bps = _edit_basis_points(candidate.text, final_text)
        was_edited = edited_text is not None and final_text != candidate.text

        draft = await self._outbound_message_service.create_draft(
            tenant_id=tenant_id,
            conversation_thread_id=run.conversation_thread_id,
            channel_connection_id=thread.channel_connection_id,
            kind=OutboundMessageKind.FREE_FORM_TEXT,
            plaintext=final_text.encode("utf-8"),
            encoding=ContentEncoding.UTF8,
            provider_template_id=None,
            created_by_user_id=context.user.id,
            actor_roles=context.membership.roles,
            audit_context=audit_context,
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )

        async with self._uow_factory() as uow:
            await uow.reply_suggestion_events.append(
                ReplySuggestionEvent(
                    id=self._uuid_factory(),
                    tenant_id=tenant_id,
                    run_id=run_id,
                    event_type=(
                        ReplySuggestionEventType.EDITED
                        if was_edited
                        else ReplySuggestionEventType.SELECTED
                    ),
                    actor_user_id=context.user.id,
                    candidate_id=candidate_id,
                    outbound_message_id=None,
                    metadata={
                        "candidate_key": candidate.candidate_key.value,
                        "edit_basis_points": edit_bps,
                    },
                    occurred_at=now,
                )
            )
            await uow.reply_suggestion_events.append(
                ReplySuggestionEvent(
                    id=self._uuid_factory(),
                    tenant_id=tenant_id,
                    run_id=run_id,
                    event_type=ReplySuggestionEventType.DRAFT_CREATED,
                    actor_user_id=context.user.id,
                    candidate_id=candidate_id,
                    outbound_message_id=draft.id,
                    metadata={"candidate_key": candidate.candidate_key.value},
                    occurred_at=now,
                )
            )
            await append_required_audit_event(
                uow.audit_events,
                reply_suggestion_selected_event(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    candidate_key=candidate.candidate_key.value,
                    edit_basis_points=edit_bps,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()

        return ReplySelectionResult(run=run, candidate=candidate, draft=draft)

    async def reject_run(
        self,
        *,
        context: TenantContext,
        run_id: UUID,
        audit_context: AuditContext,
    ) -> ReplySuggestionRun:
        _require_access(context)
        tenant_id = context.tenant.id
        now = self._clock.now()
        async with self._uow_factory() as uow:
            run = await uow.reply_suggestion_runs.get(tenant_id=tenant_id, run_id=run_id)
            if run is None:
                raise ReplySuggestionServiceError("run unavailable")
            await self._assert_thread_access(
                uow=uow,
                tenant_id=tenant_id,
                thread_id=run.conversation_thread_id,
                roles=context.membership.roles,
                user_id=context.user.id,
            )
            updated = replace(run, updated_at=now)
            await uow.reply_suggestion_events.append(
                ReplySuggestionEvent(
                    id=self._uuid_factory(),
                    tenant_id=tenant_id,
                    run_id=run_id,
                    event_type=ReplySuggestionEventType.REJECTED,
                    actor_user_id=context.user.id,
                    candidate_id=None,
                    outbound_message_id=None,
                    metadata={},
                    occurred_at=now,
                )
            )
            await append_required_audit_event(
                uow.audit_events,
                reply_suggestion_rejected_event(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
        return updated

    async def _load_ai_policy(
        self,
        *,
        tenant_id: UUID,
    ) -> TenantAiPolicyRecord | None:
        async with self._uow_factory() as uow:
            return await uow.tenant_ai_policies.get_by_tenant_id(
                tenant_id=tenant_id,
            )

    async def _load_sanitized_messages(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        audit_context: AuditContext,
        actor_id: UUID,
    ) -> tuple[tuple[tuple[UUID, str], ...], tuple[UUID, ...], tuple[str, ...]]:
        uow = self._uow_factory()
        async with uow:
            if not isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
                raise ReplySuggestionServiceError("persistence unavailable")
            rows = (
                (
                    await uow.session.execute(
                        select(MessageRow)
                        .where(
                            MessageRow.tenant_id == tenant_id,
                            MessageRow.conversation_thread_id == thread_id,
                        )
                        .order_by(MessageRow.sent_at.asc(), MessageRow.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            content_ids = [row.content_id for row in rows if row.content_id is not None]
            sanitizations_by_content: dict[UUID, object] = {}
            for content_id in content_ids:
                sanitization = await uow.content_sanitizations.get_completed_by_source(
                    tenant_id=tenant_id,
                    source_content_id=content_id,
                    policy_version=SANITIZATION_POLICY_VERSION,
                )
                if sanitization is not None and sanitization.sanitized_content_id is not None:
                    sanitizations_by_content[content_id] = sanitization

        occurred_at = self._clock.now()
        decrypted_messages: list[tuple[UUID, str]] = []
        for row in rows:
            if row.content_id is None:
                continue
            sanitization = sanitizations_by_content.get(row.content_id)
            if sanitization is None:
                continue
            sanitized_content_id = getattr(sanitization, "sanitized_content_id", None)
            if sanitized_content_id is None:
                continue
            decrypted = await self._content_encryption.load_and_decrypt(
                tenant_id=tenant_id,
                content_id=sanitized_content_id,
                purpose=ContentAccessPurpose.AI_ANALYSIS,
                occurred_at=occurred_at,
                audit_context=audit_context,
                actor_type=AuditActorType.USER,
                actor_id=actor_id,
                audit_event_id=self._uuid_factory(),
            )
            if (
                decrypted.kind is not EncryptedContentKind.SANITIZED_MESSAGE
                or decrypted.encoding is not ContentEncoding.UTF8
            ):
                continue
            decrypted_messages.append((row.id, decrypted.as_utf8_text()))

        if rows and not decrypted_messages:
            raise ReplySuggestionSanitizationMissingError("sanitized transcript unavailable")

        try:
            assembled = assemble_reply_context(decrypted_messages)
        except ReplyContextTooLargeError as exc:
            raise ReplySuggestionInputTooLargeError(str(exc)) from exc

        return assembled.messages, assembled.evidence_message_ids, assembled.structured_summary

    def _build_candidates(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        validated: object,
        created_at: object,
    ) -> tuple[ReplySuggestionCandidate, ...]:
        from closeros.domain.reply_suggestion import ValidatedReplySuggestionOutput

        if not isinstance(validated, ValidatedReplySuggestionOutput):
            raise TypeError("validated must be ValidatedReplySuggestionOutput")

        def _require_list(
            value: object,
            *,
            field_name: str,
        ) -> list[object]:
            if not isinstance(value, list):
                raise TypeError(f"{field_name} must be a list")
            return value

        def _candidate_from_payload(
            payload: dict[str, object],
            *,
            is_recommended: bool,
        ) -> ReplySuggestionCandidate:
            product_reference_values = _require_list(
                payload["product_references"],
                field_name="product_references",
            )
            product_references: list[ReplyProductReference] = []

            for item in product_reference_values:
                if not isinstance(item, dict):
                    raise TypeError("product_references items must be mappings")

                product_references.append(
                    ReplyProductReference(
                        product_id=UUID(str(item["product_id"])),
                        variant_id=UUID(str(item["variant_id"])),
                    )
                )

            confidence_value = payload["confidence_basis_points"]
            if not isinstance(confidence_value, int) or isinstance(confidence_value, bool):
                raise TypeError("confidence_basis_points must be an int")

            evidence_values = _require_list(
                payload["evidence_message_ids"],
                field_name="evidence_message_ids",
            )
            citation_values = _require_list(
                payload["knowledge_citations"],
                field_name="knowledge_citations",
            )
            warning_values = _require_list(
                payload["warnings"],
                field_name="warnings",
            )

            return ReplySuggestionCandidate(
                id=self._uuid_factory(),
                tenant_id=tenant_id,
                run_id=run_id,
                candidate_key=ReplyCandidateKey(str(payload["candidate_key"])),
                text=str(payload["text"]),
                objective=str(payload["objective"]),
                confidence_basis_points=confidence_value,
                evidence_message_ids=tuple(UUID(str(item)) for item in evidence_values),
                product_references=tuple(product_references),
                knowledge_citation_ids=tuple(UUID(str(item)) for item in citation_values),
                warnings=tuple(str(item) for item in warning_values),
                is_recommended=is_recommended,
                created_at=created_at,  # type: ignore[arg-type]
            )

        recommended = _candidate_from_payload(validated.recommended, is_recommended=True)
        alternatives = tuple(
            _candidate_from_payload(item, is_recommended=False) for item in validated.alternatives
        )
        return (recommended, *alternatives)

    async def _finalize_blocked(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        failure_code: ReplyFailureCode,
        audit_context: AuditContext,
        actor_id: UUID,
    ) -> ReplySuggestionView:
        now = self._clock.now()
        async with self._uow_factory() as uow:
            current = await uow.reply_suggestion_runs.get(tenant_id=tenant_id, run_id=run_id)
            if current is None:
                raise ReplySuggestionServiceError("run unavailable")
            blocked = replace(
                current,
                status=ReplySuggestionStatus.BLOCKED,
                failure_code=failure_code,
                updated_at=now,
                completed_at=now,
            )
            await uow.reply_suggestion_runs.save(blocked)
            await uow.reply_suggestion_events.append(
                ReplySuggestionEvent(
                    id=self._uuid_factory(),
                    tenant_id=tenant_id,
                    run_id=run_id,
                    event_type=ReplySuggestionEventType.BLOCKED,
                    actor_user_id=None,
                    candidate_id=None,
                    outbound_message_id=None,
                    metadata={"reason_code": failure_code.value},
                    occurred_at=now,
                )
            )
            await append_required_audit_event(
                uow.audit_events,
                reply_suggestion_blocked_event(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    reason_code=failure_code.value,
                    provider_code=blocked.provider_code or "unknown",
                    purpose_code=AiPurpose.REPLY_SUGGESTION.value,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
        return ReplySuggestionView(run=blocked, candidates=())

    async def _finalize_failed(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        failure_code: ReplyFailureCode,
        input_digest: bytes,
        audit_context: AuditContext,
        actor_id: UUID,
    ) -> ReplySuggestionView:
        now = self._clock.now()
        async with self._uow_factory() as uow:
            current = await uow.reply_suggestion_runs.get(tenant_id=tenant_id, run_id=run_id)
            if current is None:
                raise ReplySuggestionServiceError("run unavailable")
            failed = replace(
                current,
                status=ReplySuggestionStatus.FAILED,
                failure_code=failure_code,
                input_digest=input_digest,
                updated_at=now,
                completed_at=now,
            )
            await uow.reply_suggestion_runs.save(failed)
            await uow.reply_suggestion_events.append(
                ReplySuggestionEvent(
                    id=self._uuid_factory(),
                    tenant_id=tenant_id,
                    run_id=run_id,
                    event_type=ReplySuggestionEventType.BLOCKED,
                    actor_user_id=None,
                    candidate_id=None,
                    outbound_message_id=None,
                    metadata={"reason_code": failure_code.value},
                    occurred_at=now,
                )
            )
            await append_required_audit_event(
                uow.audit_events,
                reply_suggestion_blocked_event(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    reason_code=failure_code.value,
                    provider_code=failed.provider_code or "unknown",
                    purpose_code=AiPurpose.REPLY_SUGGESTION.value,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
        return ReplySuggestionView(run=failed, candidates=())

    async def _assert_thread_access(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        thread_id: UUID,
        roles: frozenset[Role],
        user_id: UUID,
    ) -> None:
        if not _is_manager_only(roles):
            return
        if not isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
            raise ReplySuggestionAccessDeniedError("access denied")
        statement = select(ManagerAssignmentRow.manager_user_id).where(
            ManagerAssignmentRow.tenant_id == tenant_id,
            ManagerAssignmentRow.conversation_thread_id == thread_id,
        )
        result = (await uow.session.execute(statement)).scalar_one_or_none()
        if result != user_id:
            raise ReplySuggestionAccessDeniedError("access denied")
