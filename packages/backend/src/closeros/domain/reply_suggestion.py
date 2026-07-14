"""Reply suggestion bounded context (Block V1-3). Separate from conversation analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

REPLY_PROMPT_VERSION = "v1-reply-prompt-v1"
REPLY_RUBRIC_VERSION = "v1-reply-rubric-v1"
MAX_REPLY_CANDIDATES = 3
MAX_REPLY_TEXT_CHARS = 2_000
MAX_OBJECTIVE_CHARS = 128
MAX_EXPLANATION_CHARS = 512
MAX_WARNING_CHARS = 256
MAX_WARNINGS_PER_CANDIDATE = 8
MAX_EVIDENCE_PER_CANDIDATE = 12
MAX_PRODUCT_REFS_PER_CANDIDATE = 5
MAX_KNOWLEDGE_CITATIONS = 8
MAX_MISSING_INFORMATION = 12
MAX_EDIT_DISTANCE_BASIS_POINTS = 10_000
CONFIDENCE_BASIS_POINTS_MAX = 10_000


class ReplySuggestionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    EXPIRED = "expired"


class ReplyCandidateKey(StrEnum):
    RECOMMENDED = "recommended"
    CONCISE = "concise"
    CONSULTATIVE = "consultative"
    CONFIDENT = "confident"


class ReplyCustomerIntent(StrEnum):
    PURCHASE_CONSIDERATION = "purchase_consideration"
    INFORMATION_REQUEST = "information_request"
    OBJECTION = "objection"
    SCHEDULING = "scheduling"
    SUPPORT = "support"
    UNKNOWN = "unknown"


class ReplySalesStage(StrEnum):
    DISCOVERY = "discovery"
    OFFER = "offer"
    OBJECTION_HANDLING = "objection_handling"
    CLOSING = "closing"
    FOLLOW_UP = "follow_up"
    UNKNOWN = "unknown"


class ReplyUrgency(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReplyActionCode(StrEnum):
    ASK_BUDGET = "ask_budget"
    CONFIRM_PRODUCT = "confirm_product"
    SHARE_AVAILABILITY = "share_availability"
    OFFER_DELIVERY_INFO = "offer_delivery_info"
    SCHEDULE_CALL = "schedule_call"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    CLARIFY_REQUIREMENT = "clarify_requirement"
    ACKNOWLEDGE_AND_WAIT = "acknowledge_and_wait"


class ReplySuggestionEventType(StrEnum):
    REQUESTED = "requested"
    GENERATED = "generated"
    BLOCKED = "blocked"
    SHOWN = "shown"
    SELECTED = "selected"
    EDITED = "edited"
    REJECTED = "rejected"
    DRAFT_CREATED = "draft_created"
    APPROVED = "approved"
    SENT = "sent"
    CUSTOMER_REPLIED = "customer_replied"
    BOOKED = "booked"
    WON = "won"
    LOST = "lost"


class ReplyCostStatus(StrEnum):
    UNKNOWN = "unknown"
    KNOWN = "known"
    NOT_APPLICABLE = "not_applicable"


class ReplyFailureCode(StrEnum):
    POLICY_DISABLED = "policy_disabled"
    PURPOSE_NOT_ALLOWED = "purpose_not_allowed"
    BUDGET_EXCEEDED = "budget_exceeded"
    SANITIZATION_MISSING = "sanitization_missing"
    INPUT_TOO_LARGE = "input_too_large"
    PROVIDER_FAILURE = "provider_failure"
    OUTPUT_INVALID = "output_invalid"
    GROUNDING_FAILED = "grounding_failed"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    ACCESS_DENIED = "access_denied"


def confidence_label(basis_points: int) -> str:
    percent = basis_points // 100
    if percent <= 49:
        return "low"
    if percent <= 74:
        return "medium"
    if percent <= 89:
        return "high"
    return "very_high"


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


def _validate_bounded_text(value: object, *, field_name: str, max_length: int) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} exceeds allowed length")
    return normalized


def _validate_confidence(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value < 0 or value > CONFIDENCE_BASIS_POINTS_MAX:
        raise ValueError(f"{field_name} out of range")
    return value


@dataclass(frozen=True, slots=True)
class ReplyCustomerState:
    intent: ReplyCustomerIntent
    sales_stage: ReplySalesStage
    primary_objection: str | None
    urgency: ReplyUrgency
    language: str
    missing_information: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.intent, ReplyCustomerIntent):
            raise TypeError("intent must be a ReplyCustomerIntent")
        if not isinstance(self.sales_stage, ReplySalesStage):
            raise TypeError("sales_stage must be a ReplySalesStage")
        if not isinstance(self.urgency, ReplyUrgency):
            raise TypeError("urgency must be a ReplyUrgency")
        language = _validate_bounded_text(self.language, field_name="language", max_length=16)
        object.__setattr__(self, "language", language.casefold())
        if self.primary_objection is not None:
            object.__setattr__(
                self,
                "primary_objection",
                _validate_bounded_text(
                    self.primary_objection, field_name="primary_objection", max_length=64
                ),
            )
        if not isinstance(self.missing_information, tuple):
            raise TypeError("missing_information must be a tuple")
        if len(self.missing_information) > MAX_MISSING_INFORMATION:
            raise ValueError("missing_information exceeds bound")
        normalized = tuple(
            _validate_bounded_text(item, field_name="missing_information", max_length=64)
            for item in self.missing_information
        )
        object.__setattr__(self, "missing_information", normalized)


@dataclass(frozen=True, slots=True)
class ReplyNextBestAction:
    action_code: ReplyActionCode
    explanation: str

    def __post_init__(self) -> None:
        if not isinstance(self.action_code, ReplyActionCode):
            raise TypeError("action_code must be a ReplyActionCode")
        object.__setattr__(
            self,
            "explanation",
            _validate_bounded_text(
                self.explanation, field_name="explanation", max_length=MAX_EXPLANATION_CHARS
            ),
        )


@dataclass(frozen=True, slots=True)
class ReplyProductReference:
    product_id: UUID
    variant_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_id", _validate_uuid(self.product_id, "product_id"))
        object.__setattr__(self, "variant_id", _validate_uuid(self.variant_id, "variant_id"))


@dataclass(frozen=True, slots=True)
class ReplySuggestionCandidate:
    id: UUID
    tenant_id: UUID
    run_id: UUID
    candidate_key: ReplyCandidateKey
    text: str
    objective: str
    confidence_basis_points: int
    evidence_message_ids: tuple[UUID, ...]
    product_references: tuple[ReplyProductReference, ...]
    knowledge_citation_ids: tuple[UUID, ...]
    warnings: tuple[str, ...]
    is_recommended: bool
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "run_id", _validate_uuid(self.run_id, "run_id"))
        if not isinstance(self.candidate_key, ReplyCandidateKey):
            raise TypeError("candidate_key must be a ReplyCandidateKey")
        object.__setattr__(
            self,
            "text",
            _validate_bounded_text(self.text, field_name="text", max_length=MAX_REPLY_TEXT_CHARS),
        )
        object.__setattr__(
            self,
            "objective",
            _validate_bounded_text(
                self.objective, field_name="objective", max_length=MAX_OBJECTIVE_CHARS
            ),
        )
        object.__setattr__(
            self,
            "confidence_basis_points",
            _validate_confidence(self.confidence_basis_points, "confidence_basis_points"),
        )
        if not isinstance(self.evidence_message_ids, tuple):
            raise TypeError("evidence_message_ids must be a tuple")
        if len(self.evidence_message_ids) > MAX_EVIDENCE_PER_CANDIDATE:
            raise ValueError("evidence exceeds bound")
        if len(self.product_references) > MAX_PRODUCT_REFS_PER_CANDIDATE:
            raise ValueError("product_references exceeds bound")
        if len(self.warnings) > MAX_WARNINGS_PER_CANDIDATE:
            raise ValueError("warnings exceeds bound")
        if type(self.is_recommended) is not bool:
            raise TypeError("is_recommended must be a bool")
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )


@dataclass(frozen=True, slots=True)
class ReplySuggestionRun:
    id: UUID
    tenant_id: UUID
    conversation_thread_id: UUID
    lead_id: UUID | None
    requested_by_user_id: UUID
    status: ReplySuggestionStatus
    prompt_version: str
    rubric_version: str
    provider_code: str | None
    model_code: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_milliseconds: int | None
    provider_request_id: str | None
    cost_status: ReplyCostStatus
    estimated_cost_microunits: int | None
    failure_code: ReplyFailureCode | None
    customer_state: ReplyCustomerState | None
    next_best_action: ReplyNextBestAction | None
    escalation_reason: str | None
    idempotency_key: str | None
    input_digest: bytes | None
    output_digest: bytes | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self,
            "conversation_thread_id",
            _validate_uuid(self.conversation_thread_id, "conversation_thread_id"),
        )
        if self.lead_id is not None:
            object.__setattr__(self, "lead_id", _validate_uuid(self.lead_id, "lead_id"))
        object.__setattr__(
            self,
            "requested_by_user_id",
            _validate_uuid(self.requested_by_user_id, "requested_by_user_id"),
        )
        if not isinstance(self.status, ReplySuggestionStatus):
            raise TypeError("status must be a ReplySuggestionStatus")
        if not isinstance(self.cost_status, ReplyCostStatus):
            raise TypeError("cost_status must be a ReplyCostStatus")
        if self.cost_status is ReplyCostStatus.KNOWN and self.estimated_cost_microunits is None:
            raise ValueError("known cost requires estimated_cost_microunits")
        if (
            self.cost_status is ReplyCostStatus.UNKNOWN
            and self.estimated_cost_microunits is not None
            and self.estimated_cost_microunits == 0
        ):
            # Zero with unknown status is forbidden: callers must leave cost null.
            raise ValueError("unknown cost must not record zero as known money")
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_timezone_aware_datetime(self.updated_at, "updated_at")
        )
        if type(self.version) is not int or self.version < 1:
            raise ValueError("version must be a positive int")


@dataclass(frozen=True, slots=True)
class ReplySuggestionEvent:
    id: UUID
    tenant_id: UUID
    run_id: UUID
    event_type: ReplySuggestionEventType
    actor_user_id: UUID | None
    candidate_id: UUID | None
    outbound_message_id: UUID | None
    metadata: Mapping[str, str | int | bool]
    occurred_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "run_id", _validate_uuid(self.run_id, "run_id"))
        if not isinstance(self.event_type, ReplySuggestionEventType):
            raise TypeError("event_type must be a ReplySuggestionEventType")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        object.__setattr__(
            self, "occurred_at", _validate_timezone_aware_datetime(self.occurred_at, "occurred_at")
        )


@dataclass(frozen=True, slots=True)
class ValidatedReplySuggestionOutput:
    purpose: str
    customer_state: ReplyCustomerState
    next_best_action: ReplyNextBestAction
    recommended: dict[str, object]
    alternatives: tuple[dict[str, object], ...]
    escalation: str | None
    output_digest: bytes
    canonical_json: str


class ReplySuggestionError(ValueError):
    """Domain or application error for reply suggestions."""


class ReplySuggestionAccessDeniedError(PermissionError):
    """Raised when the actor lacks scope for the conversation."""
