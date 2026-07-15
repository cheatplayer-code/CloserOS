"""Tests for provider telemetry in Reply Copilot HTTP responses."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from closeros.domain.reply_suggestion import (
    ReplyCostStatus,
    ReplySuggestionRun,
    ReplySuggestionStatus,
)
from closeros_api.reply_suggestion_router import _run_response


def test_run_response_exposes_non_sensitive_provider_telemetry() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
    run = ReplySuggestionRun(
        id=uuid4(),
        tenant_id=uuid4(),
        conversation_thread_id=uuid4(),
        lead_id=None,
        requested_by_user_id=uuid4(),
        status=ReplySuggestionStatus.COMPLETED,
        prompt_version="v1-reply-prompt-v1",
        rubric_version="v1-reply-rubric-v1",
        provider_code="openai",
        model_code="deepseek-v4-flash",
        input_tokens=121,
        output_tokens=44,
        latency_milliseconds=703,
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

    response = _run_response(run, ())

    assert response.provider_code == "openai"
    assert response.model_code == "deepseek-v4-flash"
    assert response.input_tokens == 121
    assert response.output_tokens == 44
    assert response.latency_milliseconds == 703
    assert response.cost_status == "unknown"
    assert response.estimated_cost_microunits is None
