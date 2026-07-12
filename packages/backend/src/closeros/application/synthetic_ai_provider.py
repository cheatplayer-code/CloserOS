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
        if request.purpose is not AiPurpose.CONVERSATION_ANALYSIS:
            raise SyntheticProviderError("synthetic provider only supports conversation.analysis")
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
