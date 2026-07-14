"""Strict JSON validator for reply.suggestion AI output."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from uuid import UUID

from closeros.application.privacy_detector import detect_sensitive_data
from closeros.domain.ai_analysis import AiFailureCode, AiPurpose
from closeros.domain.reply_suggestion import (
    MAX_EVIDENCE_PER_CANDIDATE,
    MAX_EXPLANATION_CHARS,
    MAX_KNOWLEDGE_CITATIONS,
    MAX_MISSING_INFORMATION,
    MAX_PRODUCT_REFS_PER_CANDIDATE,
    MAX_REPLY_CANDIDATES,
    MAX_REPLY_TEXT_CHARS,
    MAX_WARNING_CHARS,
    MAX_WARNINGS_PER_CANDIDATE,
    ReplyActionCode,
    ReplyCandidateKey,
    ReplyCustomerIntent,
    ReplyCustomerState,
    ReplyNextBestAction,
    ReplySalesStage,
    ReplySuggestionError,
    ReplyUrgency,
    ValidatedReplySuggestionOutput,
)

_CHAIN_OF_THOUGHT_KEYS = frozenset(
    {
        "chain_of_thought",
        "chain_of_thought_summary",
        "cot",
        "reasoning",
        "thoughts",
        "deliberation",
        "scratchpad",
        "internal_notes",
    }
)
_TOP_LEVEL = frozenset(
    {
        "purpose",
        "customer_state",
        "next_best_action",
        "recommended_candidate",
        "alternatives",
        "escalation",
    }
)
_CUSTOMER_STATE_KEYS = frozenset(
    {
        "intent",
        "sales_stage",
        "primary_objection",
        "urgency",
        "language",
        "missing_information",
    }
)
_CANDIDATE_KEYS = frozenset(
    {
        "candidate_key",
        "text",
        "objective",
        "confidence_basis_points",
        "evidence_message_ids",
        "product_references",
        "knowledge_citations",
        "warnings",
    }
)
_URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
_DISCOUNT_PATTERN = re.compile(
    r"(?:\b\d{1,2}\s?%|\b\d{1,2}\s?процент|\bскидк|\bdiscount\b|\bакци)",
    re.IGNORECASE,
)
_PRICE_CLAIM_PATTERN = re.compile(
    r"(?:цена|стоимость|price|стоит)\s*[:=]?\s*\d[\d\s]{2,}",
    re.IGNORECASE,
)


class ReplyOutputValidationError(ReplySuggestionError):
    def __init__(self, *, failure_code: AiFailureCode, detail: str = "invalid output") -> None:
        self.failure_code = failure_code
        super().__init__(detail)


def _reject_cot(payload: dict[str, Any]) -> None:
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if key in _CHAIN_OF_THOUGHT_KEYS:
                    raise ReplyOutputValidationError(
                        failure_code=AiFailureCode.UNSAFE_OUTPUT, detail="cot_forbidden"
                    )
                stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)


def _require_keys(payload: dict[str, Any], allowed: frozenset[str], *, label: str) -> None:
    keys = frozenset(payload)
    if keys != allowed:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail=f"{label}_keys"
        )


def _parse_uuid_list(values: Any, *, field_name: str, max_count: int) -> tuple[UUID, ...]:
    if not isinstance(values, list):
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail=field_name
        )
    if len(values) > max_count:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail=f"{field_name}_bound"
        )
    result: list[UUID] = []
    for item in values:
        try:
            result.append(UUID(str(item)))
        except (TypeError, ValueError) as exc:
            raise ReplyOutputValidationError(
                failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail=field_name
            ) from exc
    return tuple(result)


def _validate_candidate(
    raw: dict[str, Any],
    *,
    allowed_evidence: frozenset[UUID],
    allowed_products: frozenset[tuple[UUID, UUID]],
    allowed_chunks: frozenset[UUID],
) -> dict[str, Any]:
    _require_keys(raw, _CANDIDATE_KEYS, label="candidate")
    try:
        key = ReplyCandidateKey(str(raw["candidate_key"]))
    except ValueError as exc:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="candidate_key"
        ) from exc
    text = str(raw["text"])
    if len(text) > MAX_REPLY_TEXT_CHARS or not text.strip():
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="text"
        )
    if _URL_PATTERN.search(text):
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.UNSAFE_OUTPUT, detail="arbitrary_link"
        )
    if detect_sensitive_data(text).findings:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.UNSAFE_OUTPUT, detail="pii_output"
        )
    objective = str(raw["objective"])
    confidence = raw["confidence_basis_points"]
    if type(confidence) is not int or not 0 <= confidence <= 10_000:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="confidence"
        )
    evidence = _parse_uuid_list(
        raw["evidence_message_ids"],
        field_name="evidence_message_ids",
        max_count=MAX_EVIDENCE_PER_CANDIDATE,
    )
    if any(item not in allowed_evidence for item in evidence):
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.UNSAFE_OUTPUT, detail="invalid_evidence"
        )
    product_refs_raw = raw["product_references"]
    if (
        not isinstance(product_refs_raw, list)
        or len(product_refs_raw) > MAX_PRODUCT_REFS_PER_CANDIDATE
    ):
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="product_references"
        )
    product_refs: list[dict[str, str]] = []
    for item in product_refs_raw:
        if not isinstance(item, dict):
            raise ReplyOutputValidationError(
                failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="product_ref"
            )
        try:
            product_id = UUID(str(item["product_id"]))
            variant_id = UUID(str(item["variant_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ReplyOutputValidationError(
                failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="product_ref"
            ) from exc
        if (product_id, variant_id) not in allowed_products:
            raise ReplyOutputValidationError(
                failure_code=AiFailureCode.UNSAFE_OUTPUT, detail="unknown_product"
            )
        # Reject free-text price/discount overrides
        if "amount_minor" in item or "currency" in item or "discount" in item:
            raise ReplyOutputValidationError(
                failure_code=AiFailureCode.UNSAFE_OUTPUT, detail="unsupported_claim"
            )
        product_refs.append({"product_id": str(product_id), "variant_id": str(variant_id)})
    if _DISCOUNT_PATTERN.search(text):
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.UNSAFE_OUTPUT, detail="unsupported_discount"
        )
    if _PRICE_CLAIM_PATTERN.search(text) and not product_refs:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.UNSAFE_OUTPUT, detail="unsupported_price_claim"
        )
    citations = _parse_uuid_list(
        raw["knowledge_citations"],
        field_name="knowledge_citations",
        max_count=MAX_KNOWLEDGE_CITATIONS,
    )
    if any(item not in allowed_chunks for item in citations):
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.UNSAFE_OUTPUT, detail="unknown_citation"
        )
    warnings_raw = raw["warnings"]
    if not isinstance(warnings_raw, list) or len(warnings_raw) > MAX_WARNINGS_PER_CANDIDATE:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="warnings"
        )
    warnings: list[str] = []
    for warning in warnings_raw:
        text_warning = str(warning).strip()
        if not text_warning or len(text_warning) > MAX_WARNING_CHARS:
            raise ReplyOutputValidationError(
                failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="warning"
            )
        warnings.append(text_warning)
    return {
        "candidate_key": key.value,
        "text": text.strip(),
        "objective": objective.strip(),
        "confidence_basis_points": confidence,
        "evidence_message_ids": [str(item) for item in evidence],
        "product_references": product_refs,
        "knowledge_citations": [str(item) for item in citations],
        "warnings": warnings,
    }


def validate_reply_suggestion_json(
    *,
    raw_text: str,
    allowed_evidence_message_ids: frozenset[UUID],
    allowed_product_variant_ids: frozenset[tuple[UUID, UUID]],
    allowed_knowledge_chunk_ids: frozenset[UUID],
) -> ValidatedReplySuggestionOutput:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="json"
        ) from exc
    if not isinstance(payload, dict):
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="object"
        )
    _reject_cot(payload)
    _require_keys(payload, _TOP_LEVEL, label="top")
    if payload.get("purpose") != AiPurpose.REPLY_SUGGESTION.value:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="purpose"
        )
    state_raw = payload["customer_state"]
    if not isinstance(state_raw, dict):
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="customer_state"
        )
    _require_keys(state_raw, _CUSTOMER_STATE_KEYS, label="customer_state")
    missing = state_raw["missing_information"]
    if not isinstance(missing, list) or len(missing) > MAX_MISSING_INFORMATION:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="missing_information"
        )
    try:
        customer_state = ReplyCustomerState(
            intent=ReplyCustomerIntent(str(state_raw["intent"])),
            sales_stage=ReplySalesStage(str(state_raw["sales_stage"])),
            primary_objection=(
                str(state_raw["primary_objection"])
                if state_raw["primary_objection"] is not None
                else None
            ),
            urgency=ReplyUrgency(str(state_raw["urgency"])),
            language=str(state_raw["language"]),
            missing_information=tuple(str(item) for item in missing),
        )
    except (TypeError, ValueError) as exc:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="customer_state_enum"
        ) from exc

    nba_raw = payload["next_best_action"]
    if not isinstance(nba_raw, dict):
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="next_best_action"
        )
    try:
        next_best = ReplyNextBestAction(
            action_code=ReplyActionCode(str(nba_raw["action_code"])),
            explanation=str(nba_raw["explanation"]),
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="action"
        ) from exc
    if len(next_best.explanation) > MAX_EXPLANATION_CHARS:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="explanation"
        )

    recommended_raw = payload["recommended_candidate"]
    if not isinstance(recommended_raw, dict):
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="recommended"
        )
    recommended = _validate_candidate(
        recommended_raw,
        allowed_evidence=allowed_evidence_message_ids,
        allowed_products=allowed_product_variant_ids,
        allowed_chunks=allowed_knowledge_chunk_ids,
    )
    if recommended["candidate_key"] != ReplyCandidateKey.RECOMMENDED.value:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="recommended_key"
        )

    alternatives_raw = payload["alternatives"]
    if not isinstance(alternatives_raw, list):
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="alternatives"
        )
    if len(alternatives_raw) + 1 > MAX_REPLY_CANDIDATES:
        raise ReplyOutputValidationError(
            failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="candidate_count"
        )
    alternatives: list[dict[str, Any]] = []
    seen_keys = {ReplyCandidateKey.RECOMMENDED.value}
    for item in alternatives_raw:
        if not isinstance(item, dict):
            raise ReplyOutputValidationError(
                failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="alternative"
            )
        parsed = _validate_candidate(
            item,
            allowed_evidence=allowed_evidence_message_ids,
            allowed_products=allowed_product_variant_ids,
            allowed_chunks=allowed_knowledge_chunk_ids,
        )
        if parsed["candidate_key"] in seen_keys:
            raise ReplyOutputValidationError(
                failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="duplicate_key"
            )
        if parsed["candidate_key"] == ReplyCandidateKey.RECOMMENDED.value:
            raise ReplyOutputValidationError(
                failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="alt_recommended"
            )
        seen_keys.add(parsed["candidate_key"])
        alternatives.append(parsed)

    escalation = payload["escalation"]
    if escalation is not None:
        escalation = str(escalation).strip()
        if not escalation or len(escalation) > MAX_EXPLANATION_CHARS:
            raise ReplyOutputValidationError(
                failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID, detail="escalation"
            )

    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).digest()
    return ValidatedReplySuggestionOutput(
        purpose=AiPurpose.REPLY_SUGGESTION.value,
        customer_state=customer_state,
        next_best_action=next_best,
        recommended=recommended,
        alternatives=tuple(alternatives),
        escalation=escalation,
        output_digest=digest,
        canonical_json=canonical,
    )
