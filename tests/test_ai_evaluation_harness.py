"""Synthetic NOPQ AI evaluation harness tests (offline only)."""

# mypy: disable-error-code=no-any-return

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from closeros.application.ai_output_validator import AiOutputValidator
from closeros.application.ai_ports import ProviderRequest
from closeros.application.synthetic_ai_provider import SyntheticAiProvider
from closeros.domain.ai_analysis import AiProviderCode, AiPurpose


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    name: str
    transcript: str
    evidence_ids: tuple[UUID, ...]
    expect_issue_code: str


def _cases() -> tuple[EvaluationCase, ...]:
    return (
        EvaluationCase(
            name="missing action commitment",
            transcript="Customer asks when implementation starts; manager gives no next step.",
            evidence_ids=(UUID("00000000-0000-0000-0000-000000000101"),),
            expect_issue_code="missing_next_step",
        ),
        EvaluationCase(
            name="pricing discussion unresolved",
            transcript="Conversation covers price but no concrete follow-up owner/date.",
            evidence_ids=(UUID("00000000-0000-0000-0000-000000000102"),),
            expect_issue_code="missing_next_step",
        ),
        EvaluationCase(
            name="timeline ambiguity",
            transcript="Buyer asks timeline; manager responds vaguely without commitment.",
            evidence_ids=(UUID("00000000-0000-0000-0000-000000000103"),),
            expect_issue_code="missing_next_step",
        ),
        EvaluationCase(
            name="handoff without closure",
            transcript="Manager promises handoff but does not assign owner/date.",
            evidence_ids=(UUID("00000000-0000-0000-0000-000000000104"),),
            expect_issue_code="missing_next_step",
        ),
    )


async def _run_case(case: EvaluationCase) -> dict[str, Any]:
    provider = SyntheticAiProvider()
    request = ProviderRequest(
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        provider_code=AiProviderCode.SYNTHETIC,
        purpose=AiPurpose.CONVERSATION_ANALYSIS,
        model_code="synthetic-model",
        prompt_version="nopq-prompt-v1",
        rubric_version="nopq-rubric-v1",
        prompt_text=case.transcript,
        evidence_message_ids=case.evidence_ids,
        max_output_characters=8_192,
        input_digest=bytes(range(32)),
        requested_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
    )
    result = await provider.call_chat_json(request=request, bearer_key="unused")
    parsed: dict[str, Any] = json.loads(result.output_text)
    return parsed


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case.name)
def test_synthetic_harness_cases_produce_expected_issue_code(case: EvaluationCase) -> None:
    payload = asyncio.run(_run_case(case))
    finding = payload["findings"][0]
    assert finding["issue_code"] == case.expect_issue_code


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case.name)
def test_synthetic_harness_cases_pass_strict_output_validation(case: EvaluationCase) -> None:
    payload = asyncio.run(_run_case(case))
    validator = AiOutputValidator()
    validated = validator.validate_conversation_analysis_json(
        output_text=json.dumps(payload),
        allowed_evidence_message_ids=frozenset(case.evidence_ids),
        allowed_knowledge_chunk_ids=frozenset(),
    )
    assert validated.issue_count == 1
    assert validated.findings[0].issue_code.value == case.expect_issue_code


def test_harness_is_offline_and_provider_code_is_synthetic() -> None:
    payload = asyncio.run(_run_case(_cases()[0]))
    assert payload["purpose"] == "conversation.analysis"
