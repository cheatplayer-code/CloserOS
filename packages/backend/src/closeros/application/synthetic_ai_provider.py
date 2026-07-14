"""Deterministic synthetic AI provider for local and CI tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from closeros.application.ai_ports import AiProvider, ProviderRequest, ProviderResult
from closeros.domain.ai_analysis import AiProviderCode, AiPurpose, AiUsage


class SyntheticProviderError(Exception):
    """Raised when synthetic provider request is invalid."""


@dataclass(frozen=True, slots=True)
class SyntheticAiProvider(AiProvider):
    provider_code: AiProviderCode = AiProviderCode.SYNTHETIC

    async def call_chat_json(
        self,
        *,
        request: ProviderRequest,
        bearer_key: str,
    ) -> ProviderResult:
        _ = bearer_key
        if request.purpose is AiPurpose.CONVERSATION_ANALYSIS:
            return self._conversation_analysis_result(request)
        if request.purpose is AiPurpose.REPLY_SUGGESTION:
            return self._reply_suggestion_result(request)
        raise SyntheticProviderError("synthetic provider purpose is not supported")

    def _conversation_analysis_result(self, request: ProviderRequest) -> ProviderResult:
        if not request.evidence_message_ids:
            raise SyntheticProviderError("synthetic provider requires evidence message IDs")
        finding_payload = {
            "issue_code": "missing_next_step",
            "severity": "medium",
            "confidence_basis_points": 6200,
            "explanation": "Conversation lacks a concrete next action commitment.",
            "recommended_action": "Confirm an explicit next step and responsible owner.",
            "evidence_message_ids": [str(request.evidence_message_ids[0])],
            "knowledge_citations": [],
        }
        response_payload = {
            "purpose": AiPurpose.CONVERSATION_ANALYSIS.value,
            "findings": [finding_payload],
        }
        output_text = json.dumps(response_payload, separators=(",", ":"), sort_keys=True)
        return ProviderResult(
            provider_code=self.provider_code,
            model_code=request.model_code,
            purpose=request.purpose,
            output_text=output_text,
            usage=AiUsage(
                input_tokens=64,
                output_tokens=48,
                latency_milliseconds=1,
                estimated_cost_microunits=0,
            ),
            completed_at=datetime.now(tz=UTC),
        )

    def _reply_suggestion_result(self, request: ProviderRequest) -> ProviderResult:
        if not request.evidence_message_ids:
            raise SyntheticProviderError("synthetic provider requires evidence message IDs")
        evidence = [str(message_id) for message_id in request.evidence_message_ids[:2]]
        candidate_base = {
            "objective": "clarify_next_step",
            "confidence_basis_points": 7600,
            "evidence_message_ids": evidence,
            "product_references": [],
            "knowledge_citations": [],
            "warnings": [],
        }
        response_payload = {
            "purpose": AiPurpose.REPLY_SUGGESTION.value,
            "customer_state": {
                "intent": "information_request",
                "sales_stage": "discovery",
                "primary_objection": None,
                "urgency": "medium",
                "language": "ru",
                "missing_information": ["budget"],
            },
            "next_best_action": {
                "action_code": "ask_budget",
                "explanation": "Confirm budget before quoting a specific offer.",
            },
            "recommended_candidate": {
                "candidate_key": "recommended",
                "text": "Спасибо за интерес. Подскажите, пожалуйста, на какой бюджет вы ориентируетесь?",
                **candidate_base,
            },
            "alternatives": [
                {
                    "candidate_key": "concise",
                    "text": "Какой бюджет вам удобен?",
                    **candidate_base,
                },
                {
                    "candidate_key": "consultative",
                    "text": (
                        "Чтобы предложить подходящий вариант, уточните, "
                        "пожалуйста, комфортный для вас бюджет."
                    ),
                    **candidate_base,
                },
            ],
            "escalation": None,
        }
        output_text = json.dumps(response_payload, separators=(",", ":"), sort_keys=True)
        return ProviderResult(
            provider_code=self.provider_code,
            model_code=request.model_code,
            purpose=request.purpose,
            output_text=output_text,
            usage=AiUsage(
                input_tokens=96,
                output_tokens=128,
                latency_milliseconds=2,
                estimated_cost_microunits=0,
            ),
            completed_at=datetime.now(tz=UTC),
        )
