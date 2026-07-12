"""Unit tests for AI input gate policy and sanitization checks."""

# mypy: disable-error-code=arg-type

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from closeros.application.ai_input_gate import AiInputGate, AiInputGateError, GateMessage
from closeros.domain.ai_analysis import AiFailureCode, AiProviderCode, AiPurpose, TenantAiPolicy
from closeros.domain.privacy_redaction import AnalysisEligibility


def _policy(
    *, tenant_id: UUID, enabled: bool = True, max_messages: int = 10, max_chars: int = 2_000
) -> TenantAiPolicy:
    now = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    return TenantAiPolicy(
        tenant_id=tenant_id,
        enabled=enabled,
        provider_code=AiProviderCode.SYNTHETIC,
        allowed_purposes=frozenset({AiPurpose.CONVERSATION_ANALYSIS}),
        processing_region_code="kz",
        prompt_version="nopq-prompt-v1",
        rubric_version="nopq-rubric-v1",
        maximum_messages_per_request=max_messages,
        maximum_sanitized_characters=max_chars,
        maximum_output_characters=1_024,
        daily_input_token_budget=1_000,
        daily_output_token_budget=1_000,
        daily_cost_budget_microunits=100_000,
        maximum_retrieved_knowledge_chunks=4,
        created_at=now,
        updated_at=now,
        version=1,
    )


def _message(
    message_id: str, text: str, eligibility: AnalysisEligibility = AnalysisEligibility.ELIGIBLE
) -> GateMessage:
    return GateMessage(
        message_id=UUID(message_id),
        sanitized_text=text,
        eligibility=eligibility,
    )


def test_verify_and_hash_accepts_clean_sanitized_messages() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    gate = AiInputGate()
    accepted = gate.verify_and_hash(
        tenant_id=tenant_id,
        policy=_policy(tenant_id=tenant_id),
        purpose=AiPurpose.CONVERSATION_ANALYSIS,
        messages=(
            _message("00000000-0000-0000-0000-000000000101", "Customer asks for pricing options."),
            _message(
                "00000000-0000-0000-0000-000000000102", "Manager requests preferred start date."
            ),
        ),
    )
    assert accepted.message_count == 2
    assert accepted.total_characters == len(accepted.input_text)
    assert len(accepted.input_digest) == 32


def test_verify_and_hash_is_deterministic_for_same_input() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    gate = AiInputGate()
    kwargs = dict(
        tenant_id=tenant_id,
        policy=_policy(tenant_id=tenant_id),
        purpose=AiPurpose.CONVERSATION_ANALYSIS,
        messages=(_message("00000000-0000-0000-0000-000000000101", "Clean synthetic text"),),
    )
    a = gate.verify_and_hash(**kwargs)
    b = gate.verify_and_hash(**kwargs)
    assert a.input_digest == b.input_digest
    assert a.input_text == b.input_text


def test_verify_and_hash_rejects_when_policy_tenant_does_not_match() -> None:
    gate = AiInputGate()
    with pytest.raises(AiInputGateError) as error:
        gate.verify_and_hash(
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            policy=_policy(tenant_id=UUID("00000000-0000-0000-0000-000000000002")),
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            messages=(_message("00000000-0000-0000-0000-000000000101", "Clean synthetic text"),),
        )
    assert error.value.failure_code is AiFailureCode.PURPOSE_NOT_ALLOWED


def test_verify_and_hash_rejects_when_policy_disabled() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    gate = AiInputGate()
    with pytest.raises(AiInputGateError) as error:
        gate.verify_and_hash(
            tenant_id=tenant_id,
            policy=_policy(tenant_id=tenant_id, enabled=False),
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            messages=(_message("00000000-0000-0000-0000-000000000101", "Clean synthetic text"),),
        )
    assert error.value.failure_code is AiFailureCode.POLICY_DISABLED


def test_verify_and_hash_rejects_when_purpose_not_allowed() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    gate = AiInputGate()
    with pytest.raises(AiInputGateError) as error:
        gate.verify_and_hash(
            tenant_id=tenant_id,
            policy=_policy(tenant_id=tenant_id),
            purpose=AiPurpose.REPLY_SUGGESTION,
            messages=(_message("00000000-0000-0000-0000-000000000101", "Clean synthetic text"),),
        )
    assert error.value.failure_code is AiFailureCode.PURPOSE_NOT_ALLOWED


def test_verify_and_hash_rejects_empty_messages() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    gate = AiInputGate()
    with pytest.raises(AiInputGateError) as error:
        gate.verify_and_hash(
            tenant_id=tenant_id,
            policy=_policy(tenant_id=tenant_id),
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            messages=(),
        )
    assert error.value.failure_code is AiFailureCode.SANITIZATION_MISSING


def test_verify_and_hash_rejects_when_message_count_limit_exceeded() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    gate = AiInputGate()
    with pytest.raises(AiInputGateError) as error:
        gate.verify_and_hash(
            tenant_id=tenant_id,
            policy=_policy(tenant_id=tenant_id, max_messages=1),
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            messages=(
                _message("00000000-0000-0000-0000-000000000101", "A"),
                _message("00000000-0000-0000-0000-000000000102", "B"),
            ),
        )
    assert error.value.failure_code is AiFailureCode.INPUT_TOO_LARGE


def test_verify_and_hash_rejects_non_eligible_message() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    gate = AiInputGate()
    with pytest.raises(AiInputGateError) as error:
        gate.verify_and_hash(
            tenant_id=tenant_id,
            policy=_policy(tenant_id=tenant_id),
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            messages=(
                _message(
                    "00000000-0000-0000-0000-000000000101",
                    "Clean synthetic text",
                    AnalysisEligibility.BLOCKED,
                ),
            ),
        )
    assert error.value.failure_code is AiFailureCode.SANITIZATION_BLOCKED


def test_verify_and_hash_rejects_if_sensitive_data_leaks_into_sanitized_text() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    gate = AiInputGate()
    with pytest.raises(AiInputGateError) as error:
        gate.verify_and_hash(
            tenant_id=tenant_id,
            policy=_policy(tenant_id=tenant_id),
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            messages=(
                _message(
                    "00000000-0000-0000-0000-000000000101",
                    "Synthetic contact: unsafe@example.test",
                ),
            ),
        )
    assert error.value.failure_code is AiFailureCode.SANITIZATION_BLOCKED


@pytest.mark.parametrize("text_size", [70, 100, 150])
def test_verify_and_hash_rejects_if_total_text_exceeds_policy(text_size: int) -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    gate = AiInputGate()
    with pytest.raises(AiInputGateError) as error:
        gate.verify_and_hash(
            tenant_id=tenant_id,
            policy=_policy(tenant_id=tenant_id, max_chars=32),
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            messages=(_message("00000000-0000-0000-0000-000000000101", "x" * text_size),),
        )
    assert error.value.failure_code is AiFailureCode.INPUT_TOO_LARGE


def test_gate_message_rejects_blank_text() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        GateMessage(
            message_id=UUID("00000000-0000-0000-0000-000000000101"),
            sanitized_text="   ",
        )


def test_gate_message_rejects_non_uuid_message_id() -> None:
    with pytest.raises(TypeError, match="UUID"):
        GateMessage(
            message_id="not-uuid",
            sanitized_text="Synthetic safe text",
        )


def test_verify_and_hash_rejects_non_uuid_tenant_id() -> None:
    gate = AiInputGate()
    with pytest.raises(TypeError, match="UUID"):
        gate.verify_and_hash(
            tenant_id="bad-tenant",
            policy=_policy(tenant_id=UUID("00000000-0000-0000-0000-000000000001")),
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            messages=(_message("00000000-0000-0000-0000-000000000101", "safe text"),),
        )
