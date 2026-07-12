"""Framework-independent transactional outbox domain model."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

_DEDUPLICATION_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,127}$")
_WORKER_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_RESOURCE_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_MAX_PRIORITY = 1_000
_MIN_PRIORITY = 0
_DEFAULT_PRIORITY = 100
_DEFAULT_MAX_ATTEMPTS = 10
_MIN_SCHEMA_VERSION = 1
_MAX_SCHEMA_VERSION = 1_000

PUBLISHER_LEASE_SECONDS = 60
PROCESSOR_LEASE_SECONDS = 300

RETRY_BASE_DELAY_SECONDS = 30
RETRY_MAX_DELAY_SECONDS = 3_600
RETRY_BACKOFF_MULTIPLIER = 2


class OutboxJobKind(StrEnum):
    WEBHOOK_NORMALIZE = "webhook.normalize"
    CONTENT_REDACT = "content.redact"
    MESSAGE_ANALYZE = "message.analyze"
    NOTIFICATION_DELIVER = "notification.deliver"
    RETENTION_DELETE = "retention.delete"
    KNOWLEDGE_INDEX = "knowledge.index"
    RECONCILIATION_RUN = "reconciliation.run"
    CSV_IMPORT = "csv.import"
    METRICS_RECALCULATE = "metrics.recalculate"
    PROVIDER_MESSAGE_SEND = "provider.message.send"
    PROVIDER_TEMPLATES_SYNC = "provider.templates.sync"


class OutboxJobState(StrEnum):
    PENDING = "pending"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PROCESSING = "processing"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class OutboxJobPhase(StrEnum):
    PUBLISHER = "publisher"
    PROCESSOR = "processor"


class OutboxErrorCode(StrEnum):
    PUBLISH_FAILED = "publish_failed"
    QUEUE_UNAVAILABLE = "queue_unavailable"
    HANDLER_FAILED = "handler_failed"
    HANDLER_NOT_IMPLEMENTED = "handler_not_implemented"
    HANDLER_TIMEOUT = "handler_timeout"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    STALE_CLAIM = "stale_claim"
    TRANSITION_INVALID = "transition_invalid"
    CLAIM_EXPIRED = "claim_expired"
    MAX_ATTEMPTS_EXCEEDED = "max_attempts_exceeded"
    MALFORMED_PROVIDER_EVENT = "malformed_provider_event"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    MISSING_CANONICAL_PARENT = "missing_canonical_parent"
    ADAPTER_UNAVAILABLE = "adapter_unavailable"


class OutboxAttemptOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RECLAIMED = "reclaimed"


_GLOBAL_JOB_KINDS = frozenset({OutboxJobKind.RECONCILIATION_RUN})

_ALLOWED_TRANSITIONS: dict[OutboxJobState, frozenset[OutboxJobState]] = {
    OutboxJobState.PENDING: frozenset({OutboxJobState.PUBLISHING, OutboxJobState.CANCELLED}),
    OutboxJobState.PUBLISHING: frozenset(
        {
            OutboxJobState.PUBLISHED,
            OutboxJobState.RETRY_SCHEDULED,
            OutboxJobState.DEAD_LETTER,
            OutboxJobState.PENDING,
        }
    ),
    OutboxJobState.PUBLISHED: frozenset({OutboxJobState.PROCESSING}),
    OutboxJobState.PROCESSING: frozenset(
        {
            OutboxJobState.SUCCEEDED,
            OutboxJobState.RETRY_SCHEDULED,
            OutboxJobState.DEAD_LETTER,
            OutboxJobState.PUBLISHED,
        }
    ),
    OutboxJobState.RETRY_SCHEDULED: frozenset(
        {OutboxJobState.PUBLISHING, OutboxJobState.CANCELLED}
    ),
    OutboxJobState.SUCCEEDED: frozenset(),
    OutboxJobState.DEAD_LETTER: frozenset(),
    OutboxJobState.CANCELLED: frozenset(),
}


class OutboxError(Exception):
    """Base class for safe outbox domain failures."""


class OutboxInvariantError(OutboxError):
    """Raised when an outbox entity violates domain invariants."""


class OutboxTransitionError(OutboxError):
    """Raised when a state transition is not permitted."""


class OutboxClaimError(OutboxError):
    """Raised when a claim token, lease, or version does not match."""


def _validate_uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")
    return value


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise OutboxInvariantError(f"{field_name} must be timezone-aware")
    return value


def _validate_deduplication_key(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("deduplication_key must be a string")
    if not _DEDUPLICATION_KEY_PATTERN.fullmatch(value):
        raise OutboxInvariantError("deduplication_key format is invalid")
    return value


def _validate_worker_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("worker_id must be a string")
    if not _WORKER_ID_PATTERN.fullmatch(value):
        raise OutboxInvariantError("worker_id format is invalid")
    return value


def _validate_resource_type(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("resource_type must be a string")
    if not _RESOURCE_TYPE_PATTERN.fullmatch(value):
        raise OutboxInvariantError("resource_type format is invalid")
    return value


def _validate_priority(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError("priority must be an integer")
    if not _MIN_PRIORITY <= value <= _MAX_PRIORITY:
        raise OutboxInvariantError("priority is out of bounds")
    return value


def _validate_attempt_count(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError("attempt_count must be an integer")
    if value < 0:
        raise OutboxInvariantError("attempt_count must not be negative")
    return value


def _validate_max_attempts(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError("max_attempts must be an integer")
    if value < 1:
        raise OutboxInvariantError("max_attempts must be positive")
    return value


def _validate_schema_version(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError("schema_version must be an integer")
    if not _MIN_SCHEMA_VERSION <= value <= _MAX_SCHEMA_VERSION:
        raise OutboxInvariantError("schema_version is out of bounds")
    return value


def _validate_version(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError("version must be an integer")
    if value < 1:
        raise OutboxInvariantError("version must be positive")
    return value


def _validate_job_tenant_scope(*, job_kind: OutboxJobKind, tenant_id: UUID | None) -> None:
    if job_kind in _GLOBAL_JOB_KINDS:
        if tenant_id is not None:
            raise OutboxInvariantError("global job kinds require tenant_id to be absent")
        return
    if tenant_id is None:
        raise OutboxInvariantError("tenant-scoped job kinds require tenant_id")


def _assert_transition(current: OutboxJobState, target: OutboxJobState) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise OutboxTransitionError("outbox state transition is not permitted")


def _assert_claim_token(job: OutboxJob, claim_token: UUID) -> None:
    if job.claim_token != claim_token:
        raise OutboxClaimError("claim token does not match")


def _assert_claim_not_expired(job: OutboxJob, *, now: datetime) -> None:
    if job.claim_expires_at is None:
        raise OutboxClaimError("claim expiry is missing")
    if now >= job.claim_expires_at:
        raise OutboxClaimError("claim lease has expired")


def _assert_expected_version(job: OutboxJob, expected_version: int) -> None:
    if job.version != expected_version:
        raise OutboxClaimError("outbox job version does not match")


def calculate_retry_delay_seconds(*, attempt_count: int) -> int:
    """Deterministic exponential backoff without jitter.

    Attempt 1 -> 30s, attempt 2 -> 60s, attempt 3 -> 120s, capped at 3600s.
    """
    if attempt_count < 1:
        raise OutboxInvariantError("attempt_count must be positive for retry delay")
    exponent = attempt_count - 1
    delay = RETRY_BASE_DELAY_SECONDS * (RETRY_BACKOFF_MULTIPLIER**exponent)
    return int(min(RETRY_MAX_DELAY_SECONDS, delay))


@dataclass(frozen=True, slots=True)
class OutboxJobReference:
    resource_type: str
    resource_id: UUID
    schema_version: int
    tenant_id: UUID | None = None
    secondary_id: UUID | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_type", _validate_resource_type(self.resource_type))
        _validate_uuid(self.resource_id, "resource_id")
        _validate_schema_version(self.schema_version)
        if self.tenant_id is not None:
            _validate_uuid(self.tenant_id, "tenant_id")
        if self.secondary_id is not None:
            _validate_uuid(self.secondary_id, "secondary_id")


@dataclass(frozen=True, slots=True)
class OutboxJob:
    id: UUID
    tenant_id: UUID | None
    job_kind: OutboxJobKind
    reference: OutboxJobReference
    deduplication_key: str
    priority: int
    state: OutboxJobState
    available_at: datetime
    created_at: datetime
    attempt_count: int
    max_attempts: int
    version: int
    claim_token: UUID | None = None
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    claim_expires_at: datetime | None = None
    published_at: datetime | None = None
    processing_started_at: datetime | None = None
    completed_at: datetime | None = None
    last_error_code: OutboxErrorCode | None = None

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        if not isinstance(self.job_kind, OutboxJobKind):
            raise TypeError("job_kind must be an OutboxJobKind")
        _validate_job_tenant_scope(job_kind=self.job_kind, tenant_id=self.tenant_id)
        if not isinstance(self.reference, OutboxJobReference):
            raise TypeError("reference must be an OutboxJobReference")
        if self.reference.tenant_id is not None and self.reference.tenant_id != self.tenant_id:
            raise OutboxInvariantError("reference tenant_id must match job tenant_id")
        object.__setattr__(
            self,
            "deduplication_key",
            _validate_deduplication_key(self.deduplication_key),
        )
        object.__setattr__(self, "priority", _validate_priority(self.priority))
        if not isinstance(self.state, OutboxJobState):
            raise TypeError("state must be an OutboxJobState")
        object.__setattr__(
            self,
            "available_at",
            _validate_timezone_aware_datetime(self.available_at, "available_at"),
        )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(self, "attempt_count", _validate_attempt_count(self.attempt_count))
        object.__setattr__(self, "max_attempts", _validate_max_attempts(self.max_attempts))
        object.__setattr__(self, "version", _validate_version(self.version))
        if self.claim_token is not None:
            _validate_uuid(self.claim_token, "claim_token")
        if self.claimed_by is not None:
            object.__setattr__(self, "claimed_by", _validate_worker_id(self.claimed_by))
        if self.claimed_at is not None:
            object.__setattr__(
                self,
                "claimed_at",
                _validate_timezone_aware_datetime(self.claimed_at, "claimed_at"),
            )
        if self.claim_expires_at is not None:
            object.__setattr__(
                self,
                "claim_expires_at",
                _validate_timezone_aware_datetime(self.claim_expires_at, "claim_expires_at"),
            )
        if self.published_at is not None:
            object.__setattr__(
                self,
                "published_at",
                _validate_timezone_aware_datetime(self.published_at, "published_at"),
            )
        if self.processing_started_at is not None:
            object.__setattr__(
                self,
                "processing_started_at",
                _validate_timezone_aware_datetime(
                    self.processing_started_at,
                    "processing_started_at",
                ),
            )
        if self.completed_at is not None:
            object.__setattr__(
                self,
                "completed_at",
                _validate_timezone_aware_datetime(self.completed_at, "completed_at"),
            )
        if self.last_error_code is not None and not isinstance(
            self.last_error_code, OutboxErrorCode
        ):
            raise TypeError("last_error_code must be an OutboxErrorCode when present")

    def __repr__(self) -> str:
        return (
            "OutboxJob("
            f"id={self.id!s}, "
            f"job_kind={self.job_kind.value!r}, "
            f"state={self.state.value!r}, "
            f"version={self.version}"
            ")"
        )


@dataclass(frozen=True, slots=True)
class OutboxJobAttempt:
    id: UUID
    job_id: UUID
    attempt_number: int
    phase: OutboxJobPhase
    started_at: datetime
    finished_at: datetime
    outcome: OutboxAttemptOutcome
    claim_token: UUID
    error_code: OutboxErrorCode | None = None

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.job_id, "job_id")
        if not isinstance(self.attempt_number, int) or self.attempt_number < 1:
            raise OutboxInvariantError("attempt_number must be a positive integer")
        if not isinstance(self.phase, OutboxJobPhase):
            raise TypeError("phase must be an OutboxJobPhase")
        object.__setattr__(
            self,
            "started_at",
            _validate_timezone_aware_datetime(self.started_at, "started_at"),
        )
        finished_at = _validate_timezone_aware_datetime(self.finished_at, "finished_at")
        if finished_at < self.started_at:
            raise OutboxInvariantError("finished_at must not be earlier than started_at")
        object.__setattr__(self, "finished_at", finished_at)
        if not isinstance(self.outcome, OutboxAttemptOutcome):
            raise TypeError("outcome must be an OutboxAttemptOutcome")
        _validate_uuid(self.claim_token, "claim_token")
        if self.error_code is not None and not isinstance(self.error_code, OutboxErrorCode):
            raise TypeError("error_code must be an OutboxErrorCode when present")

    def __repr__(self) -> str:
        return (
            "OutboxJobAttempt("
            f"job_id={self.job_id!s}, "
            f"attempt_number={self.attempt_number}, "
            f"phase={self.phase.value!r}, "
            f"outcome={self.outcome.value!r}"
            ")"
        )


def build_outbox_job(
    *,
    job_id: UUID,
    tenant_id: UUID | None,
    job_kind: OutboxJobKind,
    reference: OutboxJobReference,
    deduplication_key: str,
    created_at: datetime,
    available_at: datetime | None = None,
    priority: int = _DEFAULT_PRIORITY,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
) -> OutboxJob:
    resolved_available_at = created_at if available_at is None else available_at
    return OutboxJob(
        id=job_id,
        tenant_id=tenant_id,
        job_kind=job_kind,
        reference=reference,
        deduplication_key=deduplication_key,
        priority=priority,
        state=OutboxJobState.PENDING,
        available_at=resolved_available_at,
        created_at=created_at,
        attempt_count=0,
        max_attempts=max_attempts,
        version=1,
    )


def claim_for_publishing(
    job: OutboxJob,
    *,
    claim_token: UUID,
    worker_id: str,
    now: datetime,
    expected_version: int,
) -> OutboxJob:
    _assert_expected_version(job, expected_version)
    if job.state not in {OutboxJobState.PENDING, OutboxJobState.RETRY_SCHEDULED}:
        raise OutboxTransitionError("job is not claimable for publishing")
    if now < job.available_at:
        raise OutboxTransitionError("job is not yet available")
    _assert_transition(job.state, OutboxJobState.PUBLISHING)
    validated_worker_id = _validate_worker_id(worker_id)
    return replace(
        job,
        state=OutboxJobState.PUBLISHING,
        claim_token=claim_token,
        claimed_by=validated_worker_id,
        claimed_at=now,
        claim_expires_at=now + timedelta(seconds=PUBLISHER_LEASE_SECONDS),
        version=job.version + 1,
    )


def mark_published(
    job: OutboxJob,
    *,
    claim_token: UUID,
    now: datetime,
    expected_version: int,
) -> OutboxJob:
    _assert_expected_version(job, expected_version)
    if job.state is not OutboxJobState.PUBLISHING:
        raise OutboxTransitionError("job is not in publishing state")
    _assert_claim_token(job, claim_token)
    _assert_claim_not_expired(job, now=now)
    _assert_transition(job.state, OutboxJobState.PUBLISHED)
    return replace(
        job,
        state=OutboxJobState.PUBLISHED,
        published_at=now,
        claim_token=None,
        claimed_by=None,
        claimed_at=None,
        claim_expires_at=None,
        last_error_code=None,
        version=job.version + 1,
    )


def schedule_retry(
    job: OutboxJob,
    *,
    claim_token: UUID,
    phase: OutboxJobPhase,
    error_code: OutboxErrorCode,
    now: datetime,
    expected_version: int,
) -> OutboxJob:
    _assert_expected_version(job, expected_version)
    if phase is OutboxJobPhase.PUBLISHER and job.state is not OutboxJobState.PUBLISHING:
        raise OutboxTransitionError("job is not in publishing state")
    if phase is OutboxJobPhase.PROCESSOR and job.state is not OutboxJobState.PROCESSING:
        raise OutboxTransitionError("job is not in processing state")
    _assert_claim_token(job, claim_token)
    _assert_claim_not_expired(job, now=now)
    next_attempt_count = job.attempt_count + 1
    if next_attempt_count >= job.max_attempts:
        raise OutboxTransitionError("retry budget exhausted")
    _assert_transition(job.state, OutboxJobState.RETRY_SCHEDULED)
    delay_seconds = calculate_retry_delay_seconds(attempt_count=next_attempt_count)
    return replace(
        job,
        state=OutboxJobState.RETRY_SCHEDULED,
        attempt_count=next_attempt_count,
        available_at=now + timedelta(seconds=delay_seconds),
        claim_token=None,
        claimed_by=None,
        claimed_at=None,
        claim_expires_at=None,
        processing_started_at=None
        if phase is OutboxJobPhase.PROCESSOR
        else job.processing_started_at,
        published_at=None if phase is OutboxJobPhase.PROCESSOR else job.published_at,
        last_error_code=error_code,
        version=job.version + 1,
    )


def mark_dead_letter(
    job: OutboxJob,
    *,
    claim_token: UUID,
    error_code: OutboxErrorCode,
    now: datetime,
    expected_version: int,
) -> OutboxJob:
    _assert_expected_version(job, expected_version)
    if job.state not in {OutboxJobState.PUBLISHING, OutboxJobState.PROCESSING}:
        raise OutboxTransitionError("job is not in a dead-letterable state")
    _assert_claim_token(job, claim_token)
    _assert_claim_not_expired(job, now=now)
    _assert_transition(job.state, OutboxJobState.DEAD_LETTER)
    return replace(
        job,
        state=OutboxJobState.DEAD_LETTER,
        completed_at=now,
        claim_token=None,
        claimed_by=None,
        claimed_at=None,
        claim_expires_at=None,
        last_error_code=error_code,
        version=job.version + 1,
    )


def claim_for_processing(
    job: OutboxJob,
    *,
    claim_token: UUID,
    worker_id: str,
    now: datetime,
    expected_version: int,
) -> OutboxJob:
    _assert_expected_version(job, expected_version)
    if job.state is not OutboxJobState.PUBLISHED:
        raise OutboxTransitionError("job is not claimable for processing")
    if now < job.available_at:
        raise OutboxTransitionError("job is not yet available")
    _assert_transition(job.state, OutboxJobState.PROCESSING)
    validated_worker_id = _validate_worker_id(worker_id)
    return replace(
        job,
        state=OutboxJobState.PROCESSING,
        claim_token=claim_token,
        claimed_by=validated_worker_id,
        claimed_at=now,
        claim_expires_at=now + timedelta(seconds=PROCESSOR_LEASE_SECONDS),
        processing_started_at=now,
        version=job.version + 1,
    )


def mark_succeeded(
    job: OutboxJob,
    *,
    claim_token: UUID,
    now: datetime,
    expected_version: int,
) -> OutboxJob:
    _assert_expected_version(job, expected_version)
    if job.state is not OutboxJobState.PROCESSING:
        raise OutboxTransitionError("job is not in processing state")
    _assert_claim_token(job, claim_token)
    _assert_claim_not_expired(job, now=now)
    _assert_transition(job.state, OutboxJobState.SUCCEEDED)
    return replace(
        job,
        state=OutboxJobState.SUCCEEDED,
        completed_at=now,
        claim_token=None,
        claimed_by=None,
        claimed_at=None,
        claim_expires_at=None,
        last_error_code=None,
        version=job.version + 1,
    )


def recover_expired_publisher_claim(job: OutboxJob, *, now: datetime) -> OutboxJob:
    if job.state is not OutboxJobState.PUBLISHING:
        raise OutboxTransitionError("job is not in publishing state")
    if job.claim_expires_at is None or now < job.claim_expires_at:
        raise OutboxTransitionError("publisher claim has not expired")
    _assert_transition(job.state, OutboxJobState.PENDING)
    return replace(
        job,
        state=OutboxJobState.PENDING,
        claim_token=None,
        claimed_by=None,
        claimed_at=None,
        claim_expires_at=None,
        version=job.version + 1,
    )


def recover_expired_processor_claim(job: OutboxJob, *, now: datetime) -> OutboxJob:
    if job.state is not OutboxJobState.PROCESSING:
        raise OutboxTransitionError("job is not in processing state")
    if job.claim_expires_at is None or now < job.claim_expires_at:
        raise OutboxTransitionError("processor claim has not expired")
    _assert_transition(job.state, OutboxJobState.PUBLISHED)
    return replace(
        job,
        state=OutboxJobState.PUBLISHED,
        claim_token=None,
        claimed_by=None,
        claimed_at=None,
        claim_expires_at=None,
        processing_started_at=None,
        version=job.version + 1,
    )


__all__ = [
    "PUBLISHER_LEASE_SECONDS",
    "PROCESSOR_LEASE_SECONDS",
    "RETRY_BACKOFF_MULTIPLIER",
    "RETRY_BASE_DELAY_SECONDS",
    "RETRY_MAX_DELAY_SECONDS",
    "OutboxAttemptOutcome",
    "OutboxClaimError",
    "OutboxError",
    "OutboxErrorCode",
    "OutboxInvariantError",
    "OutboxJob",
    "OutboxJobAttempt",
    "OutboxJobKind",
    "OutboxJobPhase",
    "OutboxJobReference",
    "OutboxJobState",
    "OutboxTransitionError",
    "build_outbox_job",
    "calculate_retry_delay_seconds",
    "claim_for_processing",
    "claim_for_publishing",
    "mark_dead_letter",
    "mark_published",
    "mark_succeeded",
    "recover_expired_processor_claim",
    "recover_expired_publisher_claim",
    "schedule_retry",
]
