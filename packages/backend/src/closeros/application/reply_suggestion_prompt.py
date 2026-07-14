"""Versioned reply-suggestion prompt construction (separate from analysis)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from closeros.domain.buyer_memory import BuyerMemoryFact
from closeros.domain.product_catalog import CatalogSearchHit
from closeros.domain.reply_suggestion import REPLY_PROMPT_VERSION, REPLY_RUBRIC_VERSION


@dataclass(frozen=True, slots=True)
class ReplyPromptBundle:
    prompt_version: str
    rubric_version: str
    system_prompt: str
    user_prompt: str


def build_reply_suggestion_prompt(
    *,
    sanitized_messages: Sequence[tuple[UUID, str]],
    memory_facts: Sequence[BuyerMemoryFact],
    product_hits: Sequence[CatalogSearchHit],
    allowed_commercial_actions: Sequence[str],
    playbook_snippets: Sequence[str],
    structured_summary: Sequence[str] = (),
    tenant_language_hint: str | None = None,
) -> ReplyPromptBundle:
    """Build a bounded, grounded reply prompt. Facts not listed are unknown."""
    system_prompt = (
        "You are CloserOS sales reply copilot. "
        "Return ONLY JSON matching the required schema with purpose reply.suggestion. "
        "Never invent products, prices, discounts, stock, delivery, or links. "
        "Facts not present in tools/product candidates are unknown and must not be invented. "
        "Critical commercial facts must be referenced by product_id and variant_id only. "
        "Match the customer's language. Do not pressure or manipulate. "
        "Escalate when policy or missing critical confirmation requires it. "
        "Do not include chain-of-thought, reasoning, or hidden fields."
    )
    transcript_lines = [
        f"[{message_id}] {text}" for message_id, text in sanitized_messages
    ]
    memory_lines = [
        f"{fact.fact_type.value}={fact.normalized_value} status={fact.status.value}"
        for fact in memory_facts
    ]
    product_lines = [
        json.dumps(
            {
                "product_id": str(hit.product_id),
                "variant_id": str(hit.variant_id),
                "product_sku": hit.product_sku,
                "name": hit.product_name,
                "amount_minor": hit.amount_minor,
                "currency": hit.currency,
                "in_stock": hit.in_stock,
                "price_usable": hit.price_provenance.usable,
                "inventory_usable": hit.inventory_provenance.usable,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
        for hit in product_hits
    ]
    schema = {
        "purpose": "reply.suggestion",
        "customer_state": {
            "intent": (
                "purchase_consideration|information_request|objection|"
                "scheduling|support|unknown"
            ),
            "sales_stage": "discovery|offer|objection_handling|closing|follow_up|unknown",
            "primary_objection": "string|null",
            "urgency": "low|medium|high",
            "language": "ru|kk|en|...",
            "missing_information": ["string"],
        },
        "next_best_action": {"action_code": "ask_budget|...", "explanation": "string"},
        "recommended_candidate": {
            "candidate_key": "recommended",
            "text": "string",
            "objective": "string",
            "confidence_basis_points": 0,
            "evidence_message_ids": ["uuid"],
            "product_references": [{"product_id": "uuid", "variant_id": "uuid"}],
            "knowledge_citations": [],
            "warnings": [],
        },
        "alternatives": [
            {
                "candidate_key": "concise|consultative|confident",
                "text": "string",
                "objective": "string",
                "confidence_basis_points": 0,
                "evidence_message_ids": ["uuid"],
                "product_references": [],
                "knowledge_citations": [],
                "warnings": [],
            }
        ],
        "escalation": "string|null",
    }
    user_prompt = "\n".join(
        [
            "## Tenant communication policy",
            "No autonomous sending. Human approval required for outbound.",
            "Prohibited: inventing prices/stock/discounts; coercion; ignoring unknown facts.",
            "",
            "## Allowed commercial actions",
            ", ".join(allowed_commercial_actions) or "none",
            "",
            "## Approved playbooks",
            "\n".join(playbook_snippets) or "none",
            "",
            "## Structured buyer memory",
            "\n".join(memory_lines) or "none",
            "",
            "## Validated product candidates",
            "\n".join(product_lines) or "none",
            "",
            "## Earlier context summary (omitted verbatim turns; IDs preserved)",
            "\n".join(structured_summary) or "none",
            "",
            "## Sanitized transcript (newest last; never drop the latest customer question)",
            "\n".join(transcript_lines),
            "",
            f"## Language hint\n{tenant_language_hint or 'match customer'}",
            "",
            "## Required JSON schema",
            json.dumps(schema, ensure_ascii=False),
            "",
            "Produce exactly one recommended candidate and up to two alternatives "
            "with distinct candidate_key values.",
        ]
    )
    return ReplyPromptBundle(
        prompt_version=REPLY_PROMPT_VERSION,
        rubric_version=REPLY_RUBRIC_VERSION,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
