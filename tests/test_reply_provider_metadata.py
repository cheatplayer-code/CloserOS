"""Tests for persisting the provider metadata actually returned by the adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from closeros.application.ai_ports import ProviderResult
from closeros.application.reply_suggestion_service import _apply_provider_result_metadata
from closeros.domain.ai_analysis import AiProviderCode, AiPurpose, AiUsage
from closeros.domain.reply_suggestion import (
    ReplyCostStatus,
    ReplySuggestionRun,
    ReplySuggestionStatus,
)


def _run() -> ReplySuggestionRun:
    now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    return ReplySuggestionRun(
        id=uuid4(),
        tenant_id=uuid4(),
        conversation_thread_id=uuid4(),
        lead_id=None,
        requested_by_user_id=uuid4(),
        status=ReplySuggestionStatus.COMPLETED,
        prompt_version="v1-reply-prompt-v1",
        rubric_version="v1-reply-rubric-v1",
        provider_code="openai",
        model_code="configured-model",
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
        idempotency_key=None,
        input_digest=None,
        output_digest=None,
        created_at=now,
        updated_at=now,
        completed_at=now,
        version=1,
    )


def test_external_result_replaces_configured_metadata_with_actual_values() -> None:
    result = ProviderResult(
        provider_code=AiProviderCode.OPENAI_COMPATIBLE,
        model_code="deepseek-v4-flash",
        purpose=AiPurpose.REPLY_SUGGESTION,
        output_text='{"purpose":"reply.suggestion"}',
        usage=AiUsage(
            input_tokens=120,
            output_tokens=45,
            latency_milliseconds=678,
            estimated_cost_microunits=321,
        ),
        completed_at=datetime(2026, 7, 15, 12, 0, 1, tzinfo=UTC),
    )

    updated = _apply_provider_result_metadata(run=_run(), provider_result=result)

    assert updated.provider_code == "openai"
    assert updated.model_code == "deepseek-v4-flash"
    assert updated.input_tokens == 120
    assert updated.output_tokens == 45
    assert updated.latency_milliseconds == 678
    assert updated.cost_status is ReplyCostStatus.KNOWN
    assert updated.estimated_cost_microunits == 321


def test_synthetic_result_records_cost_as_not_applicable() -> None:
    result = ProviderResult(
        provider_code=AiProviderCode.SYNTHETIC,
        model_code="synthetic-reply-v1",
        purpose=AiPurpose.REPLY_SUGGESTION,
        output_text='{"purpose":"reply.suggestion"}',
        usage=AiUsage(
            input_tokens=10,
            output_tokens=20,
            latency_milliseconds=1,
            estimated_cost_microunits=0,
        ),
        completed_at=datetime(2026, 7, 15, 12, 0, 1, tzinfo=UTC),
    )

    updated = _apply_provider_result_metadata(run=_run(), provider_result=result)

    assert updated.provider_code == "local"
    assert updated.model_code == "synthetic-reply-v1"
    assert updated.cost_status is ReplyCostStatus.NOT_APPLICABLE
    assert updated.estimated_cost_microunits is None
