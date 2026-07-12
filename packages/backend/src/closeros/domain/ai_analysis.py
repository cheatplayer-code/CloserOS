"""Framework-independent AI analysis domain types (Block NOPQ)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

PROMPT_VERSION = "nopq-prompt-v1"
RUBRIC_VERSION = "nopq-rubric-v1"
MAX_FINDINGS_PER_RUN = 20
MAX_EXPLANATION_CHARS = 512
MAX_RECOMMENDED_ACTION_CHARS = 512
MAX_SANITIZED_MESSAGES_PER_REQUEST = 200
MAX_SANITIZED_CHARS_PER_REQUEST = 128_000
MAX_OUTPUT_CHARS = 32_768
MAX_RETRIEVED_KNOWLEDGE_CHUNKS = 8
DIGEST_SIZE_BYTES = 32
CONFIDENCE_BASIS_POINTS_MAX = 10_000

_ISSUE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class AiProviderCode(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    SYNTHETIC = "synthetic"


class AiPurpose(StrEnum):
    CONVERSATION_ANALYSIS = "conversation.analysis"
    CONVERSATION_SUMMARY = "conversation.summary"
    REPLY_SUGGESTION = "reply.suggestion"


class AiRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class AiValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    NOT_APPLICABLE = "not_applicable"


class AiFailureCode(StrEnum):
    POLICY_DISABLED = "policy_disabled"
    PURPOSE_NOT_ALLOWED = "purpose_not_allowed"
    PROVIDER_NOT_APPROVED = "provider_not_approved"
    REGION_NOT_APPROVED = "region_not_approved"
    BUDGET_EXCEEDED = "budget_exceeded"
    SANITIZATION_BLOCKED = "sanitization_blocked"
    SANITIZATION_MISSING = "sanitization_missing"
    INPUT_TOO_LARGE = "input_too_large"
    EXTERNAL_CALLS_DISABLED = "external_calls_disabled"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_OUTPUT_INVALID = "provider_output_invalid"
    UNSAFE_OUTPUT = "unsafe_output"
    UNSUPPORTED_ENCODING = "unsupported_encoding"


class FindingIssueCode(StrEnum):
    UNANSWERED_QUESTION = "unanswered_question"
    UNHANDLED_OBJECTION = "unhandled_objection"
    MISSING_NEXT_STEP = "missing_next_step"
    REPEATED_QUESTION = "repeated_question"
    HANDOFF_CONTEXT_LOSS = "handoff_context_loss"
    DISCOVERY_GAP = "discovery_gap"
    FOLLOW_UP_RISK = "follow_up_risk"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    POLICY_CONFLICT = "policy_conflict"
    FACTUAL_RISK = "factual_risk"


class FindingSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CORRECTED = "corrected"


_SUPPORTED_ISSUE_CODES: frozenset[str] = frozenset(code.value for code in FindingIssueCode)
_SUPPORTED_SEVERITIES: frozenset[str] = frozenset(code.value for code in FindingSeverity)


def _validate_uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")
    return value


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _validate_digest(value: object, field_name: str) -> bytes:
    if type(value) is not bytes:
        raise TypeError(f"{field_name} must be bytes")
    if len(value) != DIGEST_SIZE_BYTES:
        raise ValueError(f"{field_name} must contain exactly {DIGEST_SIZE_BYTES} bytes")
    return value


def _validate_bounded_text(value: object, *, field_name: str, max_length: int) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > max_length:
        raise ValueError(f"{field_name} must not exceed {max_length} characters")
    return value


def _validate_confidence_basis_points(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value < 0 or value > CONFIDENCE_BASIS_POINTS_MAX:
        raise ValueError(f"{field_name} must be between 0 and {CONFIDENCE_BASIS_POINTS_MAX}")
    return value


def _validate_non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class FindingEvidence:
    message_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "message_id", _validate_uuid(self.message_id, "message_id"))


@dataclass(frozen=True, slots=True)
class FindingKnowledgeCitation:
    chunk_id: UUID
    source_code: str
    version_number: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunk_id", _validate_uuid(self.chunk_id, "chunk_id"))
        if type(self.source_code) is not str or not self.source_code.strip():
            raise ValueError("source_code must be a non-empty string")
        if len(self.source_code) > 64:
            raise ValueError("source_code must not exceed 64 characters")
        if type(self.version_number) is not int or self.version_number < 1:
            raise ValueError("version_number must be a positive integer")


@dataclass(frozen=True, slots=True)
class ConversationFinding:
    issue_code: FindingIssueCode
    severity: FindingSeverity
    confidence_basis_points: int
    explanation: str
    recommended_action: str
    evidence: tuple[FindingEvidence, ...]
    knowledge_citations: tuple[FindingKnowledgeCitation, ...] = ()
    review_status: FindingReviewStatus = FindingReviewStatus.PENDING

    def __post_init__(self) -> None:
        if not isinstance(self.issue_code, FindingIssueCode):
            raise TypeError("issue_code must be a FindingIssueCode")
        if not isinstance(self.severity, FindingSeverity):
            raise TypeError("severity must be a FindingSeverity")
        object.__setattr__(
            self,
            "confidence_basis_points",
            _validate_confidence_basis_points(
                self.confidence_basis_points,
                "confidence_basis_points",
            ),
        )
        object.__setattr__(
            self,
            "explanation",
            _validate_bounded_text(
                self.explanation,
                field_name="explanation",
                max_length=MAX_EXPLANATION_CHARS,
            ),
        )
        object.__setattr__(
            self,
            "recommended_action",
            _validate_bounded_text(
                self.recommended_action,
                field_name="recommended_action",
                max_length=MAX_RECOMMENDED_ACTION_CHARS,
            ),
        )
        if not isinstance(self.evidence, tuple) or not self.evidence:
            raise ValueError("evidence must contain at least one FindingEvidence")
        if not all(isinstance(item, FindingEvidence) for item in self.evidence):
            raise TypeError("evidence must contain FindingEvidence items")
        if not isinstance(self.knowledge_citations, tuple):
            raise TypeError("knowledge_citations must be a tuple")
        if not all(isinstance(item, FindingKnowledgeCitation) for item in self.knowledge_citations):
            raise TypeError("knowledge_citations must contain FindingKnowledgeCitation items")
        if not isinstance(self.review_status, FindingReviewStatus):
            raise TypeError("review_status must be a FindingReviewStatus")


@dataclass(frozen=True, slots=True)
class AiUsage:
    input_tokens: int
    output_tokens: int
    latency_milliseconds: int
    estimated_cost_microunits: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "input_tokens", _validate_non_negative_int(self.input_tokens, "input_tokens")
        )
        object.__setattr__(
            self, "output_tokens", _validate_non_negative_int(self.output_tokens, "output_tokens")
        )
        object.__setattr__(
            self,
            "latency_milliseconds",
            _validate_non_negative_int(self.latency_milliseconds, "latency_milliseconds"),
        )
        object.__setattr__(
            self,
            "estimated_cost_microunits",
            _validate_non_negative_int(self.estimated_cost_microunits, "estimated_cost_microunits"),
        )


@dataclass(frozen=True, slots=True)
class AiBudget:
    daily_input_token_budget: int
    daily_output_token_budget: int
    daily_cost_budget_microunits: int
    reserved_input_tokens: int = 0
    reserved_output_tokens: int = 0
    reserved_cost_microunits: int = 0
    consumed_input_tokens: int = 0
    consumed_output_tokens: int = 0
    consumed_cost_microunits: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "daily_input_token_budget",
            "daily_output_token_budget",
            "daily_cost_budget_microunits",
            "reserved_input_tokens",
            "reserved_output_tokens",
            "reserved_cost_microunits",
            "consumed_input_tokens",
            "consumed_output_tokens",
            "consumed_cost_microunits",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_non_negative_int(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True, slots=True)
class TenantAiPolicy:
    tenant_id: UUID
    enabled: bool
    provider_code: AiProviderCode
    allowed_purposes: frozenset[AiPurpose]
    processing_region_code: str
    prompt_version: str
    rubric_version: str
    maximum_messages_per_request: int
    maximum_sanitized_characters: int
    maximum_output_characters: int
    daily_input_token_budget: int
    daily_output_token_budget: int
    daily_cost_budget_microunits: int
    maximum_retrieved_knowledge_chunks: int
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be a bool")
        if not isinstance(self.provider_code, AiProviderCode):
            raise TypeError("provider_code must be an AiProviderCode")
        if not isinstance(self.allowed_purposes, frozenset) or not self.allowed_purposes:
            raise ValueError("allowed_purposes must be a non-empty frozenset")
        if not all(isinstance(purpose, AiPurpose) for purpose in self.allowed_purposes):
            raise TypeError("allowed_purposes must contain AiPurpose values")
        if type(self.processing_region_code) is not str or not self.processing_region_code.strip():
            raise ValueError("processing_region_code must be a non-empty string")
        for field_name, max_value in (
            ("maximum_messages_per_request", MAX_SANITIZED_MESSAGES_PER_REQUEST),
            ("maximum_sanitized_characters", MAX_SANITIZED_CHARS_PER_REQUEST),
            ("maximum_output_characters", MAX_OUTPUT_CHARS),
            ("maximum_retrieved_knowledge_chunks", MAX_RETRIEVED_KNOWLEDGE_CHUNKS),
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 1 or value > max_value:
                raise ValueError(f"{field_name} must be between 1 and {max_value}")
        for field_name in (
            "daily_input_token_budget",
            "daily_output_token_budget",
            "daily_cost_budget_microunits",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_non_negative_int(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_timezone_aware_datetime(self.updated_at, "updated_at")
        )
        if type(self.version) is not int or self.version < 1:
            raise ValueError("version must be a positive integer")


@dataclass(frozen=True, slots=True)
class ConversationAnalysisRun:
    id: UUID
    tenant_id: UUID
    conversation_thread_id: UUID
    status: AiRunStatus
    purpose: AiPurpose
    provider_code: AiProviderCode
    model_code: str
    prompt_version: str
    rubric_version: str
    input_digest: bytes
    knowledge_context_digest: bytes
    output_digest: bytes | None
    validation_status: AiValidationStatus
    input_tokens: int
    output_tokens: int
    latency_milliseconds: int
    cost_microunits: int
    attempt_count: int
    claim_lease_token: UUID | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: AiFailureCode | None
    findings: tuple[ConversationFinding, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self,
            "conversation_thread_id",
            _validate_uuid(self.conversation_thread_id, "conversation_thread_id"),
        )
        if not isinstance(self.status, AiRunStatus):
            raise TypeError("status must be an AiRunStatus")
        if not isinstance(self.purpose, AiPurpose):
            raise TypeError("purpose must be an AiPurpose")
        if not isinstance(self.provider_code, AiProviderCode):
            raise TypeError("provider_code must be an AiProviderCode")
        if type(self.model_code) is not str or not self.model_code.strip():
            raise ValueError("model_code must be a non-empty string")
        object.__setattr__(
            self, "input_digest", _validate_digest(self.input_digest, "input_digest")
        )
        object.__setattr__(
            self,
            "knowledge_context_digest",
            _validate_digest(self.knowledge_context_digest, "knowledge_context_digest"),
        )
        if self.output_digest is not None:
            object.__setattr__(
                self,
                "output_digest",
                _validate_digest(self.output_digest, "output_digest"),
            )
        if not isinstance(self.validation_status, AiValidationStatus):
            raise TypeError("validation_status must be an AiValidationStatus")
        for field_name in (
            "input_tokens",
            "output_tokens",
            "latency_milliseconds",
            "cost_microunits",
            "attempt_count",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_non_negative_int(getattr(self, field_name), field_name),
            )
        if self.claim_lease_token is not None:
            object.__setattr__(
                self,
                "claim_lease_token",
                _validate_uuid(self.claim_lease_token, "claim_lease_token"),
            )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        if self.started_at is not None:
            object.__setattr__(
                self,
                "started_at",
                _validate_timezone_aware_datetime(self.started_at, "started_at"),
            )
        if self.completed_at is not None:
            object.__setattr__(
                self,
                "completed_at",
                _validate_timezone_aware_datetime(self.completed_at, "completed_at"),
            )
        if self.failure_code is not None and not isinstance(self.failure_code, AiFailureCode):
            raise TypeError("failure_code must be an AiFailureCode or None")
        if not isinstance(self.findings, tuple):
            raise TypeError("findings must be a tuple")
        if not all(isinstance(item, ConversationFinding) for item in self.findings):
            raise TypeError("findings must contain ConversationFinding items")


def issue_code_is_supported(value: str) -> bool:
    return value in _SUPPORTED_ISSUE_CODES


def severity_code_is_supported(value: str) -> bool:
    return value in _SUPPORTED_SEVERITIES
