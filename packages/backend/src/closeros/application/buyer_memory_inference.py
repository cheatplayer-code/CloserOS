"""Deterministic evidence-backed buyer memory inference helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from closeros.domain.buyer_memory import (
    DEFAULT_INFERENCE_TTL_SECONDS,
    BuyerMemoryFact,
    BuyerMemoryFactStatus,
    BuyerMemoryFactType,
)
from closeros.domain.reply_suggestion import ReplyCustomerState


def infer_memory_facts_from_customer_state(
    *,
    tenant_id: UUID,
    conversation_thread_id: UUID,
    lead_id: UUID | None,
    customer_state: ReplyCustomerState,
    source_message_id: UUID | None,
    source_analysis_id: UUID | None,
    now: datetime,
    uuid_factory: Callable[[], UUID] = uuid4,
) -> tuple[BuyerMemoryFact, ...]:
    """Create inferred facts from structured reply customer_state.

    Facts without a message source remain inferred (never auto-confirmed).
    """
    facts: list[BuyerMemoryFact] = []
    expires_at = now + timedelta(seconds=DEFAULT_INFERENCE_TTL_SECONDS)

    language = customer_state.language.strip().casefold()
    if language:
        facts.append(
            BuyerMemoryFact(
                id=uuid_factory(),
                tenant_id=tenant_id,
                conversation_thread_id=conversation_thread_id,
                lead_id=lead_id,
                fact_type=BuyerMemoryFactType.PREFERRED_LANGUAGE,
                normalized_value=language[:64],
                display_value=customer_state.language.strip()[:128],
                status=BuyerMemoryFactStatus.INFERRED,
                confidence_basis_points=7_500,
                source_message_id=source_message_id,
                source_analysis_id=source_analysis_id,
                supersedes_fact_id=None,
                observed_at=now,
                confirmed_at=None,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
                version=1,
            )
        )

    objection = customer_state.primary_objection
    if objection is not None and objection.strip():
        facts.append(
            BuyerMemoryFact(
                id=uuid_factory(),
                tenant_id=tenant_id,
                conversation_thread_id=conversation_thread_id,
                lead_id=lead_id,
                fact_type=BuyerMemoryFactType.OBJECTION,
                normalized_value=objection.strip().casefold()[:256],
                display_value=objection.strip()[:512],
                status=BuyerMemoryFactStatus.INFERRED,
                confidence_basis_points=7_200,
                source_message_id=source_message_id,
                source_analysis_id=source_analysis_id,
                supersedes_fact_id=None,
                observed_at=now,
                confirmed_at=None,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
                version=1,
            )
        )

    return tuple(facts)
