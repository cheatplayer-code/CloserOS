"""SQLAlchemy repositories for reply suggestions and buyer memory (Block V1-3)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.domain.buyer_memory import (
    BuyerMemoryFact,
    BuyerMemoryFactStatus,
    BuyerMemoryFactType,
)
from closeros.domain.reply_suggestion import (
    ReplyActionCode,
    ReplyCandidateKey,
    ReplyCostStatus,
    ReplyCustomerIntent,
    ReplyCustomerState,
    ReplyFailureCode,
    ReplyNextBestAction,
    ReplyProductReference,
    ReplySalesStage,
    ReplySuggestionCandidate,
    ReplySuggestionEvent,
    ReplySuggestionEventType,
    ReplySuggestionRun,
    ReplySuggestionStatus,
    ReplyUrgency,
)
from closeros.infrastructure.reply_suggestion_orm import (
    BuyerMemoryFactRow,
    ReplySuggestionCandidateRow,
    ReplySuggestionEventRow,
    ReplySuggestionRunRow,
)


async def _flush(session: AsyncSession) -> None:
    await session.flush()


def _customer_state_to_json(state: ReplyCustomerState) -> dict[str, Any]:
    return {
        "intent": state.intent.value,
        "sales_stage": state.sales_stage.value,
        "primary_objection": state.primary_objection,
        "urgency": state.urgency.value,
        "language": state.language,
        "missing_information": list(state.missing_information),
    }


def _customer_state_from_json(payload: dict[str, Any] | None) -> ReplyCustomerState | None:
    if payload is None:
        return None
    return ReplyCustomerState(
        intent=ReplyCustomerIntent(str(payload["intent"])),
        sales_stage=ReplySalesStage(str(payload["sales_stage"])),
        primary_objection=(
            str(payload["primary_objection"])
            if payload.get("primary_objection") is not None
            else None
        ),
        urgency=ReplyUrgency(str(payload["urgency"])),
        language=str(payload["language"]),
        missing_information=tuple(str(item) for item in payload.get("missing_information", [])),
    )


def _next_best_action_to_json(action: ReplyNextBestAction) -> dict[str, str]:
    return {
        "action_code": action.action_code.value,
        "explanation": action.explanation,
    }


def _next_best_action_from_json(payload: dict[str, Any] | None) -> ReplyNextBestAction | None:
    if payload is None:
        return None
    return ReplyNextBestAction(
        action_code=ReplyActionCode(str(payload["action_code"])),
        explanation=str(payload["explanation"]),
    )


def _uuid_list_from_json(values: list[Any]) -> tuple[UUID, ...]:
    return tuple(UUID(str(item)) for item in values)


def _product_refs_from_json(values: list[Any]) -> tuple[ReplyProductReference, ...]:
    refs: list[ReplyProductReference] = []
    for item in values:
        refs.append(
            ReplyProductReference(
                product_id=UUID(str(item["product_id"])),
                variant_id=UUID(str(item["variant_id"])),
            )
        )
    return tuple(refs)


def _product_refs_to_json(refs: tuple[ReplyProductReference, ...]) -> list[dict[str, str]]:
    return [{"product_id": str(ref.product_id), "variant_id": str(ref.variant_id)} for ref in refs]


def _run_from_row(row: ReplySuggestionRunRow) -> ReplySuggestionRun:
    failure_code = ReplyFailureCode(row.failure_code) if row.failure_code is not None else None
    return ReplySuggestionRun(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_thread_id=row.conversation_thread_id,
        lead_id=row.lead_id,
        requested_by_user_id=row.requested_by_user_id,
        status=ReplySuggestionStatus(row.status),
        prompt_version=row.prompt_version,
        rubric_version=row.rubric_version,
        provider_code=row.provider_code,
        model_code=row.model_code,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        latency_milliseconds=row.latency_milliseconds,
        provider_request_id=row.provider_request_id,
        cost_status=ReplyCostStatus(row.cost_status),
        estimated_cost_microunits=row.estimated_cost_microunits,
        failure_code=failure_code,
        customer_state=_customer_state_from_json(row.customer_state_json),
        next_best_action=_next_best_action_from_json(row.next_best_action_json),
        escalation_reason=row.escalation_reason,
        idempotency_key=row.idempotency_key,
        input_digest=row.input_digest,
        output_digest=row.output_digest,
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
        version=row.version,
    )


def _run_to_row(run: ReplySuggestionRun) -> ReplySuggestionRunRow:
    return ReplySuggestionRunRow(
        id=run.id,
        tenant_id=run.tenant_id,
        conversation_thread_id=run.conversation_thread_id,
        lead_id=run.lead_id,
        requested_by_user_id=run.requested_by_user_id,
        status=run.status.value,
        prompt_version=run.prompt_version,
        rubric_version=run.rubric_version,
        provider_code=run.provider_code,
        model_code=run.model_code,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        latency_milliseconds=run.latency_milliseconds,
        provider_request_id=run.provider_request_id,
        cost_status=run.cost_status.value,
        estimated_cost_microunits=run.estimated_cost_microunits,
        failure_code=run.failure_code.value if run.failure_code is not None else None,
        customer_state_json=(
            _customer_state_to_json(run.customer_state) if run.customer_state is not None else None
        ),
        next_best_action_json=(
            _next_best_action_to_json(run.next_best_action)
            if run.next_best_action is not None
            else None
        ),
        escalation_reason=run.escalation_reason,
        idempotency_key=run.idempotency_key,
        input_digest=run.input_digest,
        output_digest=run.output_digest,
        created_at=run.created_at,
        updated_at=run.updated_at,
        completed_at=run.completed_at,
        version=run.version,
    )


def _candidate_from_row(row: ReplySuggestionCandidateRow) -> ReplySuggestionCandidate:
    return ReplySuggestionCandidate(
        id=row.id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        candidate_key=ReplyCandidateKey(row.candidate_key),
        text=row.text,
        objective=row.objective,
        confidence_basis_points=row.confidence_basis_points,
        evidence_message_ids=_uuid_list_from_json(list(row.evidence_message_ids or [])),
        product_references=_product_refs_from_json(list(row.product_references or [])),
        knowledge_citation_ids=_uuid_list_from_json(list(row.knowledge_citation_ids or [])),
        warnings=tuple(str(item) for item in row.warnings or []),
        is_recommended=row.is_recommended,
        created_at=row.created_at,
    )


def _candidate_to_row(candidate: ReplySuggestionCandidate) -> ReplySuggestionCandidateRow:
    return ReplySuggestionCandidateRow(
        id=candidate.id,
        tenant_id=candidate.tenant_id,
        run_id=candidate.run_id,
        candidate_key=candidate.candidate_key.value,
        text=candidate.text,
        objective=candidate.objective,
        confidence_basis_points=candidate.confidence_basis_points,
        evidence_message_ids=[str(item) for item in candidate.evidence_message_ids],
        product_references=_product_refs_to_json(candidate.product_references),
        knowledge_citation_ids=[str(item) for item in candidate.knowledge_citation_ids],
        warnings=list(candidate.warnings),
        is_recommended=candidate.is_recommended,
        created_at=candidate.created_at,
    )


def _event_from_row(row: ReplySuggestionEventRow) -> ReplySuggestionEvent:
    metadata = row.metadata_json or {}
    normalized_metadata: dict[str, str | int | bool] = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, bool)):
            normalized_metadata[str(key)] = value
    return ReplySuggestionEvent(
        id=row.id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        event_type=ReplySuggestionEventType(row.event_type),
        actor_user_id=row.actor_user_id,
        candidate_id=row.candidate_id,
        outbound_message_id=row.outbound_message_id,
        metadata=normalized_metadata,
        occurred_at=row.occurred_at,
    )


def _event_to_row(event: ReplySuggestionEvent) -> ReplySuggestionEventRow:
    return ReplySuggestionEventRow(
        id=event.id,
        tenant_id=event.tenant_id,
        run_id=event.run_id,
        event_type=event.event_type.value,
        actor_user_id=event.actor_user_id,
        candidate_id=event.candidate_id,
        outbound_message_id=event.outbound_message_id,
        metadata_json=dict(event.metadata),
        occurred_at=event.occurred_at,
    )


def _fact_from_row(row: BuyerMemoryFactRow) -> BuyerMemoryFact:
    return BuyerMemoryFact(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_thread_id=row.conversation_thread_id,
        lead_id=row.lead_id,
        fact_type=BuyerMemoryFactType(row.fact_type),
        normalized_value=row.normalized_value,
        display_value=row.display_value,
        status=BuyerMemoryFactStatus(row.status),
        confidence_basis_points=row.confidence_basis_points,
        source_message_id=row.source_message_id,
        source_analysis_id=row.source_analysis_id,
        supersedes_fact_id=row.supersedes_fact_id,
        observed_at=row.observed_at,
        confirmed_at=row.confirmed_at,
        expires_at=row.expires_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )


def _fact_to_row(fact: BuyerMemoryFact) -> BuyerMemoryFactRow:
    return BuyerMemoryFactRow(
        id=fact.id,
        tenant_id=fact.tenant_id,
        conversation_thread_id=fact.conversation_thread_id,
        lead_id=fact.lead_id,
        fact_type=fact.fact_type.value,
        normalized_value=fact.normalized_value,
        display_value=fact.display_value,
        status=fact.status.value,
        confidence_basis_points=fact.confidence_basis_points,
        source_message_id=fact.source_message_id,
        source_analysis_id=fact.source_analysis_id,
        supersedes_fact_id=fact.supersedes_fact_id,
        observed_at=fact.observed_at,
        confirmed_at=fact.confirmed_at,
        expires_at=fact.expires_at,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
        version=fact.version,
    )


class SqlAlchemyReplySuggestionRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, tenant_id: UUID, run_id: UUID) -> ReplySuggestionRun | None:
        row = await self._session.get(ReplySuggestionRunRow, run_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _run_from_row(row)

    async def get_by_idempotency(
        self, *, tenant_id: UUID, idempotency_key: str
    ) -> ReplySuggestionRun | None:
        result = await self._session.execute(
            select(ReplySuggestionRunRow).where(
                ReplySuggestionRunRow.tenant_id == tenant_id,
                ReplySuggestionRunRow.idempotency_key == idempotency_key,
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else _run_from_row(row)

    async def latest_for_thread(
        self, *, tenant_id: UUID, conversation_thread_id: UUID
    ) -> ReplySuggestionRun | None:
        result = await self._session.execute(
            select(ReplySuggestionRunRow)
            .where(
                ReplySuggestionRunRow.tenant_id == tenant_id,
                ReplySuggestionRunRow.conversation_thread_id == conversation_thread_id,
            )
            .order_by(ReplySuggestionRunRow.created_at.desc(), ReplySuggestionRunRow.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return None if row is None else _run_from_row(row)

    async def save(self, run: ReplySuggestionRun) -> ReplySuggestionRun:
        existing = await self._session.get(ReplySuggestionRunRow, run.id)
        row = _run_to_row(run)
        if existing is None:
            self._session.add(row)
        else:
            for column in ReplySuggestionRunRow.__table__.columns:
                setattr(existing, column.name, getattr(row, column.name))
        await _flush(self._session)
        return run


class SqlAlchemyReplySuggestionCandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_run(
        self, *, tenant_id: UUID, run_id: UUID
    ) -> Sequence[ReplySuggestionCandidate]:
        result = await self._session.execute(
            select(ReplySuggestionCandidateRow)
            .where(
                ReplySuggestionCandidateRow.tenant_id == tenant_id,
                ReplySuggestionCandidateRow.run_id == run_id,
            )
            .order_by(ReplySuggestionCandidateRow.is_recommended.desc())
        )
        return tuple(_candidate_from_row(row) for row in result.scalars().all())

    async def get(self, *, tenant_id: UUID, candidate_id: UUID) -> ReplySuggestionCandidate | None:
        row = await self._session.get(ReplySuggestionCandidateRow, candidate_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _candidate_from_row(row)

    async def replace_for_run(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        candidates: Sequence[ReplySuggestionCandidate],
    ) -> None:
        await self._session.execute(
            delete(ReplySuggestionCandidateRow).where(
                ReplySuggestionCandidateRow.tenant_id == tenant_id,
                ReplySuggestionCandidateRow.run_id == run_id,
            )
        )
        for candidate in candidates:
            self._session.add(_candidate_to_row(candidate))
        await _flush(self._session)


class SqlAlchemyReplySuggestionEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: ReplySuggestionEvent) -> ReplySuggestionEvent:
        self._session.add(_event_to_row(event))
        await _flush(self._session)
        return event

    async def list_for_run(
        self, *, tenant_id: UUID, run_id: UUID
    ) -> Sequence[ReplySuggestionEvent]:
        result = await self._session.execute(
            select(ReplySuggestionEventRow)
            .where(
                ReplySuggestionEventRow.tenant_id == tenant_id,
                ReplySuggestionEventRow.run_id == run_id,
            )
            .order_by(ReplySuggestionEventRow.occurred_at.asc())
        )
        return tuple(_event_from_row(row) for row in result.scalars().all())


class SqlAlchemyBuyerMemoryFactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, tenant_id: UUID, fact_id: UUID) -> BuyerMemoryFact | None:
        row = await self._session.get(BuyerMemoryFactRow, fact_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _fact_from_row(row)

    async def list_for_thread(
        self, *, tenant_id: UUID, conversation_thread_id: UUID
    ) -> Sequence[BuyerMemoryFact]:
        result = await self._session.execute(
            select(BuyerMemoryFactRow)
            .where(
                BuyerMemoryFactRow.tenant_id == tenant_id,
                BuyerMemoryFactRow.conversation_thread_id == conversation_thread_id,
            )
            .order_by(BuyerMemoryFactRow.observed_at.desc())
        )
        return tuple(_fact_from_row(row) for row in result.scalars().all())

    async def list_for_lead(self, *, tenant_id: UUID, lead_id: UUID) -> Sequence[BuyerMemoryFact]:
        result = await self._session.execute(
            select(BuyerMemoryFactRow)
            .where(
                BuyerMemoryFactRow.tenant_id == tenant_id,
                BuyerMemoryFactRow.lead_id == lead_id,
            )
            .order_by(BuyerMemoryFactRow.observed_at.desc())
        )
        return tuple(_fact_from_row(row) for row in result.scalars().all())

    async def save(self, fact: BuyerMemoryFact) -> BuyerMemoryFact:
        existing = await self._session.get(BuyerMemoryFactRow, fact.id)
        row = _fact_to_row(fact)
        if existing is None:
            self._session.add(row)
        else:
            for column in BuyerMemoryFactRow.__table__.columns:
                setattr(existing, column.name, getattr(row, column.name))
        await _flush(self._session)
        return fact
