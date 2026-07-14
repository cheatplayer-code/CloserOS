"""Unit tests for reply suggestion validator, prompt, memory, and synthetic provider."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from closeros.application.ai_ports import ProviderRequest
from closeros.application.buyer_memory_inference import infer_memory_facts_from_customer_state
from closeros.application.reply_suggestion_context import (
    ReplyContextTooLargeError,
    assemble_reply_context,
)
from closeros.application.reply_suggestion_grounding import enrich_candidate_warnings_from_catalog
from closeros.application.reply_suggestion_prompt import build_reply_suggestion_prompt
from closeros.application.reply_suggestion_validator import (
    ReplyOutputValidationError,
    validate_reply_suggestion_json,
)
from closeros.application.synthetic_ai_provider import SyntheticAiProvider
from closeros.domain.ai_analysis import AiFailureCode, AiProviderCode, AiPurpose
from closeros.domain.buyer_memory import (
    BuyerMemoryFact,
    BuyerMemoryFactStatus,
    BuyerMemoryFactType,
    select_effective_memory_facts,
)
from closeros.domain.product_catalog import (
    CatalogSearchHit,
    FactProvenance,
    FactVerificationStatus,
)
from closeros.domain.reply_suggestion import (
    REPLY_PROMPT_VERSION,
    ReplyCustomerIntent,
    ReplyCustomerState,
    ReplySalesStage,
    ReplyUrgency,
    confidence_label,
)


def _valid_payload(
    *,
    evidence_id: str,
    language: str = "ru",
    text: str | None = None,
) -> dict[str, Any]:
    body = text or "Спасибо за вопрос. Уточните, пожалуйста, бюджет."
    candidate = {
        "candidate_key": "recommended",
        "text": body,
        "objective": "clarify_budget",
        "confidence_basis_points": 7600,
        "evidence_message_ids": [evidence_id],
        "product_references": [],
        "knowledge_citations": [],
        "warnings": [],
    }
    return {
        "purpose": AiPurpose.REPLY_SUGGESTION.value,
        "customer_state": {
            "intent": "information_request",
            "sales_stage": "discovery",
            "primary_objection": None,
            "urgency": "medium",
            "language": language,
            "missing_information": ["budget"],
        },
        "next_best_action": {
            "action_code": "ask_budget",
            "explanation": "Budget is missing before quoting.",
        },
        "recommended_candidate": candidate,
        "alternatives": [
            {
                **candidate,
                "candidate_key": "concise",
                "text": "Какой бюджет вам удобен?",
            },
            {
                **candidate,
                "candidate_key": "consultative",
                "text": "Подскажите комфортный бюджет, чтобы предложить вариант.",
            },
        ],
        "escalation": None,
    }


def test_prompt_version_constant() -> None:
    bundle = build_reply_suggestion_prompt(
        sanitized_messages=((uuid4(), "hello"),),
        memory_facts=(),
        product_hits=(),
        allowed_commercial_actions=("quote_list_price",),
        playbook_snippets=(),
    )
    assert bundle.prompt_version == REPLY_PROMPT_VERSION
    assert "reply.suggestion" in bundle.user_prompt
    assert "Facts not present" in bundle.system_prompt or "unknown" in bundle.system_prompt


def test_validator_accepts_russian_suggestion() -> None:
    evidence = uuid4()
    raw = json.dumps(_valid_payload(evidence_id=str(evidence), language="ru"))
    validated = validate_reply_suggestion_json(
        raw_text=raw,
        allowed_evidence_message_ids=frozenset({evidence}),
        allowed_product_variant_ids=frozenset(),
        allowed_knowledge_chunk_ids=frozenset(),
    )
    assert validated.customer_state.language == "ru"
    assert "бюджет" in str(validated.recommended["text"]).casefold()


def test_validator_accepts_kazakh_suggestion() -> None:
    evidence = uuid4()
    raw = json.dumps(
        _valid_payload(
            evidence_id=str(evidence),
            language="kk",
            text="Сұрағыңызға рахмет. Бюджетті нақтылайсыз ба?",
        )
    )
    validated = validate_reply_suggestion_json(
        raw_text=raw,
        allowed_evidence_message_ids=frozenset({evidence}),
        allowed_product_variant_ids=frozenset(),
        allowed_knowledge_chunk_ids=frozenset(),
    )
    assert validated.customer_state.language == "kk"


def test_validator_accepts_mixed_language_suggestion() -> None:
    evidence = uuid4()
    raw = json.dumps(
        _valid_payload(
            evidence_id=str(evidence),
            language="ru",
            text="Спасибо! Could you share your budget range?",
        )
    )
    validated = validate_reply_suggestion_json(
        raw_text=raw,
        allowed_evidence_message_ids=frozenset({evidence}),
        allowed_product_variant_ids=frozenset(),
        allowed_knowledge_chunk_ids=frozenset(),
    )
    assert "budget" in str(validated.recommended["text"]).casefold()


def test_validator_rejects_unknown_evidence() -> None:
    evidence = uuid4()
    other = uuid4()
    payload = _valid_payload(evidence_id=str(evidence))
    raw = json.dumps(payload)
    with pytest.raises(ReplyOutputValidationError) as exc:
        validate_reply_suggestion_json(
            raw_text=raw,
            allowed_evidence_message_ids=frozenset({other}),
            allowed_product_variant_ids=frozenset(),
            allowed_knowledge_chunk_ids=frozenset(),
        )
    assert exc.value.failure_code is AiFailureCode.UNSAFE_OUTPUT


def test_validator_rejects_cross_tenant_product() -> None:
    evidence = uuid4()
    foreign_product = uuid4()
    foreign_variant = uuid4()
    payload = _valid_payload(evidence_id=str(evidence))
    payload["recommended_candidate"]["product_references"] = [
        {"product_id": str(foreign_product), "variant_id": str(foreign_variant)}
    ]
    raw = json.dumps(payload)
    with pytest.raises(ReplyOutputValidationError) as exc:
        validate_reply_suggestion_json(
            raw_text=raw,
            allowed_evidence_message_ids=frozenset({evidence}),
            allowed_product_variant_ids=frozenset(),
            allowed_knowledge_chunk_ids=frozenset(),
        )
    assert exc.value.failure_code is AiFailureCode.UNSAFE_OUTPUT
    assert "unknown_product" in str(exc.value)


def test_validator_rejects_altered_price_in_product_ref() -> None:
    evidence = uuid4()
    product_id = uuid4()
    variant_id = uuid4()
    payload = _valid_payload(evidence_id=str(evidence))
    payload["recommended_candidate"]["product_references"] = [
        {
            "product_id": str(product_id),
            "variant_id": str(variant_id),
            "amount_minor": 1,
        }
    ]
    raw = json.dumps(payload)
    with pytest.raises(ReplyOutputValidationError) as exc:
        validate_reply_suggestion_json(
            raw_text=raw,
            allowed_evidence_message_ids=frozenset({evidence}),
            allowed_product_variant_ids=frozenset({(product_id, variant_id)}),
            allowed_knowledge_chunk_ids=frozenset(),
        )
    assert exc.value.failure_code is AiFailureCode.UNSAFE_OUTPUT


def test_validator_rejects_unsupported_discount() -> None:
    evidence = uuid4()
    payload = _valid_payload(evidence_id=str(evidence))
    payload["recommended_candidate"]["text"] = "Могу дать скидку 20% прямо сейчас"
    raw = json.dumps(payload)
    with pytest.raises(ReplyOutputValidationError) as exc:
        validate_reply_suggestion_json(
            raw_text=raw,
            allowed_evidence_message_ids=frozenset({evidence}),
            allowed_product_variant_ids=frozenset(),
            allowed_knowledge_chunk_ids=frozenset(),
        )
    assert exc.value.failure_code is AiFailureCode.UNSAFE_OUTPUT


def test_validator_rejects_pii_output() -> None:
    evidence = uuid4()
    payload = _valid_payload(evidence_id=str(evidence))
    payload["recommended_candidate"]["text"] = "Contact me at user@example.com"
    raw = json.dumps(payload)
    with pytest.raises(ReplyOutputValidationError) as exc:
        validate_reply_suggestion_json(
            raw_text=raw,
            allowed_evidence_message_ids=frozenset({evidence}),
            allowed_product_variant_ids=frozenset(),
            allowed_knowledge_chunk_ids=frozenset(),
        )
    assert exc.value.failure_code is AiFailureCode.UNSAFE_OUTPUT


def test_validator_rejects_arbitrary_links() -> None:
    evidence = uuid4()
    payload = _valid_payload(evidence_id=str(evidence))
    payload["recommended_candidate"]["text"] = "See https://evil.example/offer"
    raw = json.dumps(payload)
    with pytest.raises(ReplyOutputValidationError) as exc:
        validate_reply_suggestion_json(
            raw_text=raw,
            allowed_evidence_message_ids=frozenset({evidence}),
            allowed_product_variant_ids=frozenset(),
            allowed_knowledge_chunk_ids=frozenset(),
        )
    assert exc.value.failure_code is AiFailureCode.UNSAFE_OUTPUT


def test_validator_rejects_chain_of_thought() -> None:
    evidence = uuid4()
    payload = _valid_payload(evidence_id=str(evidence))
    payload["chain_of_thought"] = "hidden reasoning"
    raw = json.dumps(payload)
    with pytest.raises(ReplyOutputValidationError) as exc:
        validate_reply_suggestion_json(
            raw_text=raw,
            allowed_evidence_message_ids=frozenset({evidence}),
            allowed_product_variant_ids=frozenset(),
            allowed_knowledge_chunk_ids=frozenset(),
        )
    assert exc.value.failure_code is AiFailureCode.UNSAFE_OUTPUT


def test_validator_rejects_unknown_action() -> None:
    evidence = uuid4()
    payload = _valid_payload(evidence_id=str(evidence))
    payload["next_best_action"]["action_code"] = "invent_discount"
    raw = json.dumps(payload)
    with pytest.raises(ReplyOutputValidationError) as exc:
        validate_reply_suggestion_json(
            raw_text=raw,
            allowed_evidence_message_ids=frozenset({evidence}),
            allowed_product_variant_ids=frozenset(),
            allowed_knowledge_chunk_ids=frozenset(),
        )
    assert exc.value.failure_code is AiFailureCode.PROVIDER_OUTPUT_INVALID


def test_stale_stock_warning_enrichment() -> None:
    product_id = uuid4()
    variant_id = uuid4()
    now = datetime.now(tz=UTC)
    source_id = uuid4()
    price_prov = FactProvenance(
        source_id=source_id,
        source_updated_at=now,
        verification_status=FactVerificationStatus.VERIFIED,
        checked_at=now,
        usable=True,
        valid_until=now + timedelta(days=1),
    )
    inventory_prov = FactProvenance(
        source_id=source_id,
        source_updated_at=now - timedelta(days=30),
        verification_status=FactVerificationStatus.STALE,
        checked_at=now,
        usable=False,
        valid_until=now - timedelta(days=1),
    )
    hit = CatalogSearchHit(
        product_id=product_id,
        variant_id=variant_id,
        product_sku="SKU-1",
        variant_sku="SKU-1-A",
        product_name="Sofa",
        variant_display_name="Sofa Grey",
        category_code="furniture",
        amount_minor=100_000,
        currency="KZT",
        available_quantity=2,
        in_stock=True,
        attributes={},
        price_provenance=price_prov,
        inventory_provenance=inventory_prov,
        delivery_status=None,
        delivery_usable=False,
    )
    candidate = {
        "warnings": [],
        "product_references": [{"product_id": str(product_id), "variant_id": str(variant_id)}],
    }
    enriched = enrich_candidate_warnings_from_catalog(candidate, product_hits=(hit,))
    assert "stale_stock" in enriched["warnings"]


def test_memory_conflict_selection_prefers_confirmed() -> None:
    now = datetime.now(tz=UTC)
    fact_type = BuyerMemoryFactType.BUDGET_MAX
    thread_id = uuid4()
    tenant_id = uuid4()
    inferred = BuyerMemoryFact(
        id=uuid4(),
        tenant_id=tenant_id,
        conversation_thread_id=thread_id,
        lead_id=None,
        fact_type=fact_type,
        normalized_value="500000",
        display_value="500 000 KZT",
        status=BuyerMemoryFactStatus.INFERRED,
        confidence_basis_points=8000,
        source_message_id=uuid4(),
        source_analysis_id=None,
        supersedes_fact_id=None,
        observed_at=now - timedelta(days=1),
        confirmed_at=None,
        expires_at=now + timedelta(days=30),
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
        version=1,
    )
    confirmed = BuyerMemoryFact(
        id=uuid4(),
        tenant_id=tenant_id,
        conversation_thread_id=thread_id,
        lead_id=None,
        fact_type=fact_type,
        normalized_value="650000",
        display_value="650 000 KZT",
        status=BuyerMemoryFactStatus.CONFIRMED,
        confidence_basis_points=10_000,
        source_message_id=uuid4(),
        source_analysis_id=None,
        supersedes_fact_id=inferred.id,
        observed_at=now,
        confirmed_at=now,
        expires_at=None,
        created_at=now,
        updated_at=now,
        version=1,
    )
    selected = select_effective_memory_facts((inferred, confirmed), now=now)
    assert len(selected) == 1
    assert selected[0].normalized_value == "650000"
    assert selected[0].status is BuyerMemoryFactStatus.CONFIRMED


def test_memory_fact_expiration_excludes_stale() -> None:
    now = datetime.now(tz=UTC)
    expired = BuyerMemoryFact(
        id=uuid4(),
        tenant_id=uuid4(),
        conversation_thread_id=uuid4(),
        lead_id=None,
        fact_type=BuyerMemoryFactType.BUDGET_MIN,
        normalized_value="100000",
        display_value="100000",
        status=BuyerMemoryFactStatus.INFERRED,
        confidence_basis_points=8000,
        source_message_id=uuid4(),
        source_analysis_id=None,
        supersedes_fact_id=None,
        observed_at=now - timedelta(days=40),
        confirmed_at=None,
        expires_at=now - timedelta(days=1),
        created_at=now - timedelta(days=40),
        updated_at=now - timedelta(days=40),
        version=1,
    )
    assert select_effective_memory_facts((expired,), now=now) == ()


def test_memory_inference_from_customer_state() -> None:
    now = datetime.now(tz=UTC)
    state = ReplyCustomerState(
        intent=ReplyCustomerIntent.OBJECTION,
        sales_stage=ReplySalesStage.OBJECTION_HANDLING,
        primary_objection="price",
        urgency=ReplyUrgency.MEDIUM,
        language="ru",
        missing_information=("budget",),
    )
    facts = infer_memory_facts_from_customer_state(
        tenant_id=uuid4(),
        conversation_thread_id=uuid4(),
        lead_id=None,
        customer_state=state,
        source_message_id=uuid4(),
        source_analysis_id=None,
        now=now,
    )
    types = {fact.fact_type for fact in facts}
    assert BuyerMemoryFactType.PREFERRED_LANGUAGE in types
    assert BuyerMemoryFactType.OBJECTION in types
    assert all(fact.status is BuyerMemoryFactStatus.INFERRED for fact in facts)


def test_confirmed_fact_requires_source_message() -> None:
    now = datetime.now(tz=UTC)
    with pytest.raises(ValueError):
        BuyerMemoryFact(
            id=uuid4(),
            tenant_id=uuid4(),
            conversation_thread_id=uuid4(),
            lead_id=None,
            fact_type=BuyerMemoryFactType.CURRENCY,
            normalized_value="kzt",
            display_value="KZT",
            status=BuyerMemoryFactStatus.CONFIRMED,
            confidence_basis_points=10_000,
            source_message_id=None,
            source_analysis_id=None,
            supersedes_fact_id=None,
            observed_at=now,
            confirmed_at=now,
            expires_at=None,
            created_at=now,
            updated_at=now,
            version=1,
        )


def test_context_preserves_latest_and_summarizes_omitted() -> None:
    latest = uuid4()
    older = uuid4()
    assembled = assemble_reply_context(
        ((older, "x" * 100), (latest, "latest question")),
        max_messages=1,
        max_chars=10_000,
    )
    assert assembled.messages == ((latest, "latest question"),)
    assert assembled.used_summary is True
    assert any(str(older) in item for item in assembled.structured_summary)


def test_context_fails_when_latest_exceeds_budget() -> None:
    latest = uuid4()
    with pytest.raises(ReplyContextTooLargeError):
        assemble_reply_context(((latest, "x" * 50),), max_messages=10, max_chars=10)


def test_confidence_label_bands() -> None:
    assert confidence_label(1200) == "low"
    assert confidence_label(5500) == "medium"
    assert confidence_label(8000) == "high"
    assert confidence_label(9500) == "very_high"


def test_synthetic_provider_reply_purpose() -> None:
    evidence = uuid4()
    provider = SyntheticAiProvider()
    request = ProviderRequest(
        tenant_id=uuid4(),
        provider_code=AiProviderCode.SYNTHETIC,
        purpose=AiPurpose.REPLY_SUGGESTION,
        model_code="synthetic",
        prompt_version=REPLY_PROMPT_VERSION,
        rubric_version="v1-reply-rubric-v1",
        prompt_text="test",
        evidence_message_ids=(evidence,),
    )
    result = asyncio.run(provider.call_chat_json(request=request, bearer_key=""))
    payload = json.loads(result.output_text)
    assert payload["purpose"] == AiPurpose.REPLY_SUGGESTION.value
    assert payload["recommended_candidate"]["candidate_key"] == "recommended"
    assert len(payload["alternatives"]) == 2
    assert str(evidence) in payload["recommended_candidate"]["evidence_message_ids"]
    validated = validate_reply_suggestion_json(
        raw_text=result.output_text,
        allowed_evidence_message_ids=frozenset({evidence}),
        allowed_product_variant_ids=frozenset(),
        allowed_knowledge_chunk_ids=frozenset(),
    )
    assert validated.purpose == AiPurpose.REPLY_SUGGESTION.value
