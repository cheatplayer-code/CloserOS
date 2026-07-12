"""Unit tests for strict AI output validation."""

# mypy: disable-error-code=attr-defined

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest
from closeros.application.ai_output_validator import AiOutputValidationError, AiOutputValidator
from closeros.domain.ai_analysis import MAX_FINDINGS_PER_RUN, AiFailureCode, AiPurpose

EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000101")
EVIDENCE_ID_2 = UUID("00000000-0000-0000-0000-000000000102")
CHUNK_ID = UUID("00000000-0000-0000-0000-000000000201")


def _valid_payload() -> dict[str, Any]:
    return {
        "purpose": "conversation.analysis",
        "findings": [
            {
                "issue_code": "missing_next_step",
                "severity": "medium",
                "confidence_basis_points": 6200,
                "explanation": "Conversation does not confirm a clear next action.",
                "recommended_action": "Confirm date, owner, and communication channel.",
                "evidence_message_ids": [str(EVIDENCE_ID)],
                "knowledge_citations": [
                    {
                        "chunk_id": str(CHUNK_ID),
                        "source_code": "kb_sales_playbook",
                        "version_number": 1,
                    }
                ],
            }
        ],
    }


def _validate(payload: dict[str, Any]) -> object:
    validator = AiOutputValidator()
    return validator.validate_conversation_analysis_json(
        output_text=json.dumps(payload),
        allowed_evidence_message_ids=frozenset({EVIDENCE_ID, EVIDENCE_ID_2}),
        allowed_knowledge_chunk_ids=frozenset({CHUNK_ID}),
    )


def test_validate_accepts_strict_valid_payload() -> None:
    validated = _validate(_valid_payload())
    assert validated.purpose is AiPurpose.CONVERSATION_ANALYSIS
    assert validated.issue_count == 1
    assert validated.citation_count == 1
    assert len(validated.output_digest) == 32


def test_validate_is_deterministic_for_same_payload() -> None:
    a = _validate(_valid_payload())
    b = _validate(_valid_payload())
    assert a.output_digest == b.output_digest
    assert a.canonical_output_json == b.canonical_output_json


@pytest.mark.parametrize(
    "broken",
    [
        {"purpose": "conversation.analysis"},
        {"purpose": "conversation.analysis", "findings": [], "extra": 1},
    ],
)
def test_validate_rejects_invalid_top_level_keys(broken: dict[str, Any]) -> None:
    validator = AiOutputValidator()
    with pytest.raises(AiOutputValidationError) as error:
        validator.validate_conversation_analysis_json(
            output_text=json.dumps(broken),
            allowed_evidence_message_ids=frozenset({EVIDENCE_ID}),
            allowed_knowledge_chunk_ids=frozenset({CHUNK_ID}),
        )
    assert error.value.failure_code is AiFailureCode.PROVIDER_OUTPUT_INVALID


def test_validate_rejects_chain_of_thought_fields_anywhere() -> None:
    payload = _valid_payload()
    finding = payload["findings"][0]
    assert isinstance(finding, dict)
    finding["chain_of_thought"] = "hidden reasoning"
    with pytest.raises(AiOutputValidationError) as error:
        _validate(payload)
    assert error.value.failure_code is AiFailureCode.PROVIDER_OUTPUT_INVALID


def test_validate_rejects_invalid_purpose() -> None:
    payload = _valid_payload()
    payload["purpose"] = "conversation.summary"
    with pytest.raises(AiOutputValidationError):
        _validate(payload)


def test_validate_rejects_too_many_findings() -> None:
    payload: dict[str, Any] = {"purpose": "conversation.analysis", "findings": []}
    for index in range(MAX_FINDINGS_PER_RUN + 1):
        payload["findings"].append(
            {
                "issue_code": "missing_next_step",
                "severity": "medium",
                "confidence_basis_points": 6200,
                "explanation": f"Finding {index} is synthetic and safe.",
                "recommended_action": "Confirm next action.",
                "evidence_message_ids": [str(EVIDENCE_ID)],
                "knowledge_citations": [],
            }
        )
    with pytest.raises(AiOutputValidationError):
        _validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("issue_code", "unsupported_issue"),
        ("severity", "severe"),
        ("confidence_basis_points", "6200"),
    ],
)
def test_validate_rejects_invalid_core_finding_fields(field: str, value: object) -> None:
    payload = _valid_payload()
    finding = payload["findings"][0]
    assert isinstance(finding, dict)
    finding[field] = value
    with pytest.raises(AiOutputValidationError):
        _validate(payload)


def test_validate_rejects_explanation_with_sensitive_data() -> None:
    payload = _valid_payload()
    finding = payload["findings"][0]
    assert isinstance(finding, dict)
    finding["explanation"] = "Customer email is leak@example.test and should not be present."
    with pytest.raises(AiOutputValidationError) as error:
        _validate(payload)
    assert error.value.failure_code is AiFailureCode.UNSAFE_OUTPUT


def test_validate_rejects_recommended_action_with_sensitive_data() -> None:
    payload = _valid_payload()
    finding = payload["findings"][0]
    assert isinstance(finding, dict)
    finding["recommended_action"] = "Call +7 (900) 000-00-01 now."
    with pytest.raises(AiOutputValidationError) as error:
        _validate(payload)
    assert error.value.failure_code is AiFailureCode.UNSAFE_OUTPUT


def test_validate_rejects_unknown_evidence_message_id() -> None:
    payload = _valid_payload()
    finding = payload["findings"][0]
    assert isinstance(finding, dict)
    finding["evidence_message_ids"] = [str(UUID("00000000-0000-0000-0000-000000009999"))]
    with pytest.raises(AiOutputValidationError):
        _validate(payload)


def test_validate_rejects_missing_evidence_list() -> None:
    payload = _valid_payload()
    finding = payload["findings"][0]
    assert isinstance(finding, dict)
    finding["evidence_message_ids"] = []
    with pytest.raises(AiOutputValidationError):
        _validate(payload)


def test_validate_rejects_unknown_knowledge_chunk_id() -> None:
    payload = _valid_payload()
    finding = payload["findings"][0]
    assert isinstance(finding, dict)
    finding["knowledge_citations"] = [
        {
            "chunk_id": str(UUID("00000000-0000-0000-0000-000000009998")),
            "source_code": "kb_sales_playbook",
            "version_number": 1,
        }
    ]
    with pytest.raises(AiOutputValidationError):
        _validate(payload)


def test_validate_rejects_non_json_input() -> None:
    validator = AiOutputValidator()
    with pytest.raises(AiOutputValidationError):
        validator.validate_conversation_analysis_json(
            output_text="{not-json",
            allowed_evidence_message_ids=frozenset({EVIDENCE_ID}),
            allowed_knowledge_chunk_ids=frozenset({CHUNK_ID}),
        )


def test_validate_rejects_payload_json_that_still_contains_sensitive_data() -> None:
    payload = _valid_payload()
    payload["debug_email"] = "leak@example.test"
    validator = AiOutputValidator()
    with pytest.raises(AiOutputValidationError):
        validator.validate_conversation_analysis_json(
            output_text=json.dumps(payload),
            allowed_evidence_message_ids=frozenset({EVIDENCE_ID}),
            allowed_knowledge_chunk_ids=frozenset({CHUNK_ID}),
        )


def test_validate_rejects_non_frozenset_allowed_evidence_ids() -> None:
    validator = AiOutputValidator()
    with pytest.raises(TypeError, match="frozenset"):
        validator.validate_conversation_analysis_json(
            output_text=json.dumps(_valid_payload()),
            allowed_evidence_message_ids={EVIDENCE_ID},  # type: ignore[arg-type]
            allowed_knowledge_chunk_ids=frozenset({CHUNK_ID}),
        )


def test_validate_rejects_non_frozenset_allowed_knowledge_ids() -> None:
    validator = AiOutputValidator()
    with pytest.raises(TypeError, match="frozenset"):
        validator.validate_conversation_analysis_json(
            output_text=json.dumps(_valid_payload()),
            allowed_evidence_message_ids=frozenset({EVIDENCE_ID}),
            allowed_knowledge_chunk_ids={CHUNK_ID},  # type: ignore[arg-type]
        )


def test_validate_rejects_non_object_payload() -> None:
    validator = AiOutputValidator()
    with pytest.raises(AiOutputValidationError):
        validator.validate_conversation_analysis_json(
            output_text=json.dumps([_valid_payload()]),
            allowed_evidence_message_ids=frozenset({EVIDENCE_ID}),
            allowed_knowledge_chunk_ids=frozenset({CHUNK_ID}),
        )


def test_validate_rejects_invalid_citation_shape() -> None:
    payload = _valid_payload()
    finding = payload["findings"][0]
    assert isinstance(finding, dict)
    finding["knowledge_citations"] = [{"chunk_id": str(CHUNK_ID)}]
    with pytest.raises(AiOutputValidationError):
        _validate(payload)
