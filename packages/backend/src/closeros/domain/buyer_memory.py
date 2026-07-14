"""Structured Buyer Memory domain (Block V1-3). Not an opaque LLM paragraph."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

MAX_NORMALIZED_VALUE_LENGTH = 256
MAX_DISPLAY_VALUE_LENGTH = 512
CONFIDENCE_BASIS_POINTS_MAX = 10_000
HIGH_CONFIDENCE_THRESHOLD = 7_000
DEFAULT_INFERENCE_TTL_SECONDS = 30 * 24 * 60 * 60


class BuyerMemoryFactType(StrEnum):
    PREFERRED_LANGUAGE = "preferred_language"
    BUDGET_MIN = "budget_min"
    BUDGET_MAX = "budget_max"
    CURRENCY = "currency"
    PREFERRED_CATEGORY = "preferred_category"
    PREFERRED_COLOR = "preferred_color"
    PREFERRED_MATERIAL = "preferred_material"
    DIMENSION_REQUIREMENT = "dimension_requirement"
    LOCATION = "location"
    PURCHASE_TIMELINE = "purchase_timeline"
    PRODUCT_INTEREST = "product_interest"
    OBJECTION = "objection"
    CONTACT_TIME_PREFERENCE = "contact_time_preference"
    SELLER_PROMISE = "seller_promise"
    CUSTOMER_REQUESTED_FOLLOW_UP = "customer_requested_follow_up"


class BuyerMemoryFactStatus(StrEnum):
    INFERRED = "inferred"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    DELETED = "deleted"


_SENSITIVE_FORBIDDEN_TOKENS = frozenset(
    {
        "ssn",
        "passport",
        "national_id",
        "card_number",
        "cvv",
        "password",
        "secret",
        "medical",
        "diagnosis",
        "religion",
        "ethnicity",
        "sexual_orientation",
    }
)


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
    lowered = normalized.casefold()
    for token in _SENSITIVE_FORBIDDEN_TOKENS:
        if token in lowered:
            raise ValueError(f"{field_name} contains a prohibited sensitive category")
    return normalized


@dataclass(frozen=True, slots=True)
class BuyerMemoryFact:
    id: UUID
    tenant_id: UUID
    conversation_thread_id: UUID
    lead_id: UUID | None
    fact_type: BuyerMemoryFactType
    normalized_value: str
    display_value: str
    status: BuyerMemoryFactStatus
    confidence_basis_points: int
    source_message_id: UUID | None
    source_analysis_id: UUID | None
    supersedes_fact_id: UUID | None
    observed_at: datetime
    confirmed_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
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
        if not isinstance(self.fact_type, BuyerMemoryFactType):
            raise TypeError("fact_type must be a BuyerMemoryFactType")
        object.__setattr__(
            self,
            "normalized_value",
            _validate_bounded_text(
                self.normalized_value,
                field_name="normalized_value",
                max_length=MAX_NORMALIZED_VALUE_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "display_value",
            _validate_bounded_text(
                self.display_value, field_name="display_value", max_length=MAX_DISPLAY_VALUE_LENGTH
            ),
        )
        if not isinstance(self.status, BuyerMemoryFactStatus):
            raise TypeError("status must be a BuyerMemoryFactStatus")
        if type(self.confidence_basis_points) is not int:
            raise TypeError("confidence_basis_points must be an int")
        if not 0 <= self.confidence_basis_points <= CONFIDENCE_BASIS_POINTS_MAX:
            raise ValueError("confidence_basis_points out of range")
        if self.status is BuyerMemoryFactStatus.CONFIRMED and self.source_message_id is None:
            raise ValueError("confirmed facts require source_message_id")
        if self.status is BuyerMemoryFactStatus.INFERRED and self.expires_at is None:
            raise ValueError("inferred facts require expires_at")
        object.__setattr__(
            self, "observed_at", _validate_timezone_aware_datetime(self.observed_at, "observed_at")
        )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_timezone_aware_datetime(self.updated_at, "updated_at")
        )
        if type(self.version) is not int or self.version < 1:
            raise ValueError("version must be a positive int")


def select_effective_memory_facts(
    facts: Sequence[BuyerMemoryFact], *, now: datetime
) -> tuple[BuyerMemoryFact, ...]:
    """Latest confirmed explicit fact, else latest high-confidence inferred, else none.

    History is never overwritten: superseded rows remain; this selects current view.
    """
    by_type: dict[BuyerMemoryFactType, list[BuyerMemoryFact]] = {}
    for fact in facts:
        if fact.status in {
            BuyerMemoryFactStatus.DELETED,
            BuyerMemoryFactStatus.REJECTED,
            BuyerMemoryFactStatus.EXPIRED,
        }:
            continue
        if fact.expires_at is not None and fact.expires_at <= now:
            continue
        by_type.setdefault(fact.fact_type, []).append(fact)

    selected: list[BuyerMemoryFact] = []
    for _fact_type, group in by_type.items():
        confirmed = sorted(
            (item for item in group if item.status is BuyerMemoryFactStatus.CONFIRMED),
            key=lambda item: (item.confirmed_at or item.observed_at, item.id),
            reverse=True,
        )
        if confirmed:
            selected.append(confirmed[0])
            continue
        inferred = sorted(
            (
                item
                for item in group
                if item.status is BuyerMemoryFactStatus.INFERRED
                and item.confidence_basis_points >= HIGH_CONFIDENCE_THRESHOLD
            ),
            key=lambda item: (item.confidence_basis_points, item.observed_at, item.id),
            reverse=True,
        )
        if inferred:
            selected.append(inferred[0])
    return tuple(sorted(selected, key=lambda item: (item.fact_type.value, item.id)))


class BuyerMemoryError(ValueError):
    """Raised when buyer memory invariants fail."""
