"""Strict JSON output validator for AI conversation analysis results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from uuid import UUID

from closeros.application.privacy_detector import detect_sensitive_data
from closeros.domain.ai_analysis import (
    MAX_EXPLANATION_CHARS,
    MAX_FINDINGS_PER_RUN,
    MAX_RECOMMENDED_ACTION_CHARS,
    AiFailureCode,
    AiPurpose,
    ConversationFinding,
    FindingEvidence,
    FindingIssueCode,
    FindingKnowledgeCitation,
    FindingSeverity,
    issue_code_is_supported,
    severity_code_is_supported,
)

_TOP_LEVEL_KEYS = frozenset({"purpose", "findings"})
_FINDING_KEYS = frozenset(
    {
        "issue_code",
        "severity",
        "confidence_basis_points",
        "explanation",
        "recommended_action",
        "evidence_message_ids",
        "knowledge_citations",
    }
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


class AiOutputValidationError(Exception):
    """Raised when provider output violates strict NOPQ analysis constraints."""

    def __init__(self, *, failure_code: AiFailureCode) -> None:
        self.failure_code = failure_code
        super().__init__("ai output validation failed")


@dataclass(frozen=True, slots=True)
class ValidatedAiOutput:
    purpose: AiPurpose
    findings: tuple[ConversationFinding, ...]
    issue_count: int
    citation_count: int
    output_digest: bytes = field(repr=False)
    canonical_output_json: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, AiPurpose):
            raise TypeError("purpose must be an AiPurpose")
        if not isinstance(self.findings, tuple):
            raise TypeError("findings must be a tuple")
        if not all(isinstance(item, ConversationFinding) for item in self.findings):
            raise TypeError("findings must contain ConversationFinding values")
        if type(self.issue_count) is not int or self.issue_count != len(self.findings):
            raise ValueError("issue_count must equal findings length")
        if type(self.citation_count) is not int or self.citation_count < 0:
            raise ValueError("citation_count must be a non-negative int")
        if type(self.output_digest) is not bytes or len(self.output_digest) != 32:
            raise ValueError("output_digest must contain exactly 32 bytes")
        if type(self.canonical_output_json) is not str or not self.canonical_output_json:
            raise ValueError("canonical_output_json must be non-empty")


def _assert_no_chain_of_thought_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str) and key.strip().lower() in _CHAIN_OF_THOUGHT_KEYS:
                raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
            _assert_no_chain_of_thought_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_chain_of_thought_keys(nested)


def _parse_uuid(value: object, *, failure_code: AiFailureCode) -> UUID:
    if type(value) is not str or not value.strip():
        raise AiOutputValidationError(failure_code=failure_code)
    try:
        return UUID(value.strip())
    except ValueError as error:
        raise AiOutputValidationError(failure_code=failure_code) from error


class AiOutputValidator:
    def validate_conversation_analysis_json(
        self,
        *,
        output_text: str,
        allowed_evidence_message_ids: frozenset[UUID],
        allowed_knowledge_chunk_ids: frozenset[UUID],
    ) -> ValidatedAiOutput:
        if type(output_text) is not str or not output_text.strip():
            raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
        if not isinstance(allowed_evidence_message_ids, frozenset):
            raise TypeError("allowed_evidence_message_ids must be a frozenset")
        if not isinstance(allowed_knowledge_chunk_ids, frozenset):
            raise TypeError("allowed_knowledge_chunk_ids must be a frozenset")

        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as error:
            raise AiOutputValidationError(
                failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID
            ) from error
        if not isinstance(parsed, dict):
            raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
        if frozenset(parsed.keys()) != _TOP_LEVEL_KEYS:
            raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)

        _assert_no_chain_of_thought_keys(parsed)

        if parsed.get("purpose") != AiPurpose.CONVERSATION_ANALYSIS.value:
            raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
        findings_raw = parsed.get("findings")
        if not isinstance(findings_raw, list):
            raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
        if len(findings_raw) > MAX_FINDINGS_PER_RUN:
            raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)

        findings: list[ConversationFinding] = []
        citation_count = 0
        for finding_raw in findings_raw:
            if not isinstance(finding_raw, dict):
                raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
            if frozenset(finding_raw.keys()) != _FINDING_KEYS:
                raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)

            issue_code_raw = finding_raw["issue_code"]
            if type(issue_code_raw) is not str or not issue_code_is_supported(issue_code_raw):
                raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
            severity_raw = finding_raw["severity"]
            if type(severity_raw) is not str or not severity_code_is_supported(severity_raw):
                raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
            confidence_raw = finding_raw["confidence_basis_points"]
            if type(confidence_raw) is not int:
                raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
            explanation = finding_raw["explanation"]
            if type(explanation) is not str or not explanation.strip():
                raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
            if len(explanation) > MAX_EXPLANATION_CHARS:
                raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
            recommended_action = finding_raw["recommended_action"]
            if type(recommended_action) is not str or not recommended_action.strip():
                raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
            if len(recommended_action) > MAX_RECOMMENDED_ACTION_CHARS:
                raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)

            explanation_scan = detect_sensitive_data(explanation)
            action_scan = detect_sensitive_data(recommended_action)
            if explanation_scan.total_count > 0 or action_scan.total_count > 0:
                raise AiOutputValidationError(failure_code=AiFailureCode.UNSAFE_OUTPUT)

            evidence_raw = finding_raw["evidence_message_ids"]
            if not isinstance(evidence_raw, list) or not evidence_raw:
                raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
            evidence: list[FindingEvidence] = []
            for message_id_raw in evidence_raw:
                message_id = _parse_uuid(
                    message_id_raw,
                    failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID,
                )
                if message_id not in allowed_evidence_message_ids:
                    raise AiOutputValidationError(
                        failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID
                    )
                evidence.append(FindingEvidence(message_id=message_id))

            citations_raw = finding_raw["knowledge_citations"]
            if not isinstance(citations_raw, list):
                raise AiOutputValidationError(failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID)
            citations: list[FindingKnowledgeCitation] = []
            for citation_raw in citations_raw:
                if not isinstance(citation_raw, dict):
                    raise AiOutputValidationError(
                        failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID
                    )
                expected_keys = frozenset({"chunk_id", "source_code", "version_number"})
                if frozenset(citation_raw.keys()) != expected_keys:
                    raise AiOutputValidationError(
                        failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID
                    )
                chunk_id = _parse_uuid(
                    citation_raw["chunk_id"],
                    failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID,
                )
                if chunk_id not in allowed_knowledge_chunk_ids:
                    raise AiOutputValidationError(
                        failure_code=AiFailureCode.PROVIDER_OUTPUT_INVALID
                    )
                source_code = citation_raw["source_code"]
                version_number = citation_raw["version_number"]
                citations.append(
                    FindingKnowledgeCitation(
                        chunk_id=chunk_id,
                        source_code=source_code,
                        version_number=version_number,
                    )
                )
            citation_count += len(citations)
            findings.append(
                ConversationFinding(
                    issue_code=FindingIssueCode(issue_code_raw),
                    severity=FindingSeverity(severity_raw),
                    confidence_basis_points=confidence_raw,
                    explanation=explanation,
                    recommended_action=recommended_action,
                    evidence=tuple(evidence),
                    knowledge_citations=tuple(citations),
                )
            )

        for finding in findings:
            output_scan = detect_sensitive_data(
                f"{finding.explanation}\n{finding.recommended_action}"
            )
            if output_scan.total_count > 0:
                raise AiOutputValidationError(failure_code=AiFailureCode.UNSAFE_OUTPUT)
        payload_json = json.dumps(parsed, separators=(",", ":"), sort_keys=True)
        return ValidatedAiOutput(
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            findings=tuple(findings),
            issue_count=len(findings),
            citation_count=citation_count,
            output_digest=hashlib.sha256(payload_json.encode("utf-8")).digest(),
            canonical_output_json=payload_json,
        )
