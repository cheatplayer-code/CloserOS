"""Unit tests for transactional outbox domain transitions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from closeros.domain.outbox import (
    PROCESSOR_LEASE_SECONDS,
    PUBLISHER_LEASE_SECONDS,
    OutboxClaimError,
    OutboxErrorCode,
    OutboxInvariantError,
    OutboxJob,
    OutboxJobKind,
    OutboxJobPhase,
    OutboxJobReference,
    OutboxJobState,
    OutboxTransitionError,
    build_outbox_job,
    calculate_retry_delay_seconds,
    claim_for_processing,
    claim_for_publishing,
    mark_dead_letter,
    mark_published,
    mark_succeeded,
    recover_expired_processor_claim,
    recover_expired_publisher_claim,
    schedule_retry,
)

TENANT_A = UUID("00000000-0000-0000-0000-000000000001")
RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000100")
NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=UTC)
FUTURE = NOW + timedelta(hours=1)
PAST = NOW - timedelta(hours=2)


def _reference(*, tenant_id: UUID | None = TENANT_A) -> OutboxJobReference:
    return OutboxJobReference(
        tenant_id=tenant_id,
        resource_type="message",
        resource_id=RESOURCE_ID,
        schema_version=1,
    )


def _pending_job(*, available_at: datetime = NOW) -> OutboxJob:
    return build_outbox_job(
        job_id=uuid4(),
        tenant_id=TENANT_A,
        job_kind=OutboxJobKind.CONTENT_REDACT,
        reference=_reference(),
        deduplication_key="content_redact_synthetic",
        created_at=NOW,
        available_at=available_at,
    )


def test_build_outbox_job_defaults() -> None:
    job = _pending_job()
    assert job.state is OutboxJobState.PENDING
    assert job.attempt_count == 0
    assert job.version == 1
    assert job.max_attempts == 10


def test_global_job_requires_absent_tenant_id() -> None:
    with pytest.raises(
        OutboxInvariantError, match="global job kinds require tenant_id to be absent"
    ):
        build_outbox_job(
            job_id=uuid4(),
            tenant_id=TENANT_A,
            job_kind=OutboxJobKind.RECONCILIATION_RUN,
            reference=OutboxJobReference(
                resource_type="reconciliation",
                resource_id=RESOURCE_ID,
                schema_version=1,
            ),
            deduplication_key="reconciliation_run",
            created_at=NOW,
        )


def test_tenant_scoped_job_requires_tenant_id() -> None:
    with pytest.raises(OutboxInvariantError, match="tenant-scoped job kinds require tenant_id"):
        build_outbox_job(
            job_id=uuid4(),
            tenant_id=None,
            job_kind=OutboxJobKind.CONTENT_REDACT,
            reference=OutboxJobReference(
                resource_type="message",
                resource_id=RESOURCE_ID,
                schema_version=1,
            ),
            deduplication_key="content_redact_missing_tenant",
            created_at=NOW,
        )


def test_calculate_retry_delay_exponential_backoff() -> None:
    assert calculate_retry_delay_seconds(attempt_count=1) == 30
    assert calculate_retry_delay_seconds(attempt_count=2) == 60
    assert calculate_retry_delay_seconds(attempt_count=3) == 120
    assert calculate_retry_delay_seconds(attempt_count=10) == 3600


def test_calculate_retry_delay_rejects_non_positive_attempt() -> None:
    with pytest.raises(OutboxInvariantError):
        calculate_retry_delay_seconds(attempt_count=0)


def test_claim_for_publishing_sets_lease() -> None:
    job = _pending_job()
    claim_token = uuid4()
    claimed = claim_for_publishing(
        job,
        claim_token=claim_token,
        worker_id="worker-a",
        now=NOW,
        expected_version=job.version,
    )
    assert claimed.state is OutboxJobState.PUBLISHING
    assert claimed.claim_token == claim_token
    assert claimed.claim_expires_at == NOW + timedelta(seconds=PUBLISHER_LEASE_SECONDS)


def test_claim_for_publishing_rejects_future_available_at() -> None:
    job = _pending_job(available_at=FUTURE)
    with pytest.raises(OutboxTransitionError, match="not yet available"):
        claim_for_publishing(
            job,
            claim_token=uuid4(),
            worker_id="worker-a",
            now=NOW,
            expected_version=job.version,
        )


def test_claim_for_publishing_rejects_stale_version() -> None:
    job = _pending_job()
    with pytest.raises(OutboxClaimError, match="version does not match"):
        claim_for_publishing(
            job,
            claim_token=uuid4(),
            worker_id="worker-a",
            now=NOW,
            expected_version=job.version + 1,
        )


def test_mark_published_clears_claim() -> None:
    job = _pending_job()
    claim_token = uuid4()
    publishing = claim_for_publishing(
        job,
        claim_token=claim_token,
        worker_id="worker-a",
        now=NOW,
        expected_version=job.version,
    )
    published = mark_published(
        publishing,
        claim_token=claim_token,
        now=NOW,
        expected_version=publishing.version,
    )
    assert published.state is OutboxJobState.PUBLISHED
    assert published.claim_token is None
    assert published.published_at == NOW


def test_mark_published_rejects_wrong_claim_token() -> None:
    job = _pending_job()
    publishing = claim_for_publishing(
        job,
        claim_token=uuid4(),
        worker_id="worker-a",
        now=NOW,
        expected_version=job.version,
    )
    with pytest.raises(OutboxClaimError, match="claim token does not match"):
        mark_published(
            publishing,
            claim_token=uuid4(),
            now=NOW,
            expected_version=publishing.version,
        )


def test_mark_published_rejects_expired_claim() -> None:
    job = _pending_job(available_at=PAST)
    claim_token = uuid4()
    publishing = claim_for_publishing(
        job,
        claim_token=claim_token,
        worker_id="worker-a",
        now=PAST,
        expected_version=job.version,
    )
    with pytest.raises(OutboxClaimError, match="claim lease has expired"):
        mark_published(
            publishing,
            claim_token=claim_token,
            now=NOW,
            expected_version=publishing.version,
        )


def test_schedule_retry_from_publishing() -> None:
    job = _pending_job()
    claim_token = uuid4()
    publishing = claim_for_publishing(
        job,
        claim_token=claim_token,
        worker_id="worker-a",
        now=NOW,
        expected_version=job.version,
    )
    retried = schedule_retry(
        publishing,
        claim_token=claim_token,
        phase=OutboxJobPhase.PUBLISHER,
        error_code=OutboxErrorCode.QUEUE_UNAVAILABLE,
        now=NOW,
        expected_version=publishing.version,
    )
    assert retried.state is OutboxJobState.RETRY_SCHEDULED
    assert retried.attempt_count == 1
    assert retried.available_at == NOW + timedelta(seconds=30)


def test_schedule_retry_exhausted_budget_raises() -> None:
    job = build_outbox_job(
        job_id=uuid4(),
        tenant_id=TENANT_A,
        job_kind=OutboxJobKind.CONTENT_REDACT,
        reference=_reference(),
        deduplication_key="content_redact_retry_budget",
        created_at=NOW,
        max_attempts=1,
    )
    claim_token = uuid4()
    publishing = claim_for_publishing(
        job,
        claim_token=claim_token,
        worker_id="worker-a",
        now=NOW,
        expected_version=job.version,
    )
    with pytest.raises(OutboxTransitionError, match="retry budget exhausted"):
        schedule_retry(
            publishing,
            claim_token=claim_token,
            phase=OutboxJobPhase.PUBLISHER,
            error_code=OutboxErrorCode.QUEUE_UNAVAILABLE,
            now=NOW,
            expected_version=publishing.version,
        )


def test_mark_dead_letter_from_publishing() -> None:
    job = _pending_job()
    claim_token = uuid4()
    publishing = claim_for_publishing(
        job,
        claim_token=claim_token,
        worker_id="worker-a",
        now=NOW,
        expected_version=job.version,
    )
    dead = mark_dead_letter(
        publishing,
        claim_token=claim_token,
        error_code=OutboxErrorCode.MAX_ATTEMPTS_EXCEEDED,
        now=NOW,
        expected_version=publishing.version,
    )
    assert dead.state is OutboxJobState.DEAD_LETTER
    assert dead.completed_at == NOW


def test_claim_for_processing_sets_processor_lease() -> None:
    job = _pending_job()
    claim_token = uuid4()
    publishing = claim_for_publishing(
        job,
        claim_token=claim_token,
        worker_id="worker-a",
        now=NOW,
        expected_version=job.version,
    )
    published = mark_published(
        publishing,
        claim_token=claim_token,
        now=NOW,
        expected_version=publishing.version,
    )
    processing = claim_for_processing(
        published,
        claim_token=uuid4(),
        worker_id="processor-a",
        now=NOW,
        expected_version=published.version,
    )
    assert processing.state is OutboxJobState.PROCESSING
    assert processing.claim_expires_at == NOW + timedelta(seconds=PROCESSOR_LEASE_SECONDS)


def test_mark_succeeded_from_processing() -> None:
    job = _pending_job()
    pub_token = uuid4()
    publishing = claim_for_publishing(
        job,
        claim_token=pub_token,
        worker_id="worker-a",
        now=NOW,
        expected_version=job.version,
    )
    published = mark_published(
        publishing,
        claim_token=pub_token,
        now=NOW,
        expected_version=publishing.version,
    )
    proc_token = uuid4()
    processing = claim_for_processing(
        published,
        claim_token=proc_token,
        worker_id="processor-a",
        now=NOW,
        expected_version=published.version,
    )
    succeeded = mark_succeeded(
        processing,
        claim_token=proc_token,
        now=NOW,
        expected_version=processing.version,
    )
    assert succeeded.state is OutboxJobState.SUCCEEDED
    assert succeeded.completed_at == NOW


def test_recover_expired_publisher_claim() -> None:
    job = _pending_job(available_at=PAST)
    claim_token = uuid4()
    publishing = claim_for_publishing(
        job,
        claim_token=claim_token,
        worker_id="worker-a",
        now=PAST,
        expected_version=job.version,
    )
    recovered = recover_expired_publisher_claim(publishing, now=NOW)
    assert recovered.state is OutboxJobState.PENDING
    assert recovered.claim_token is None


def test_recover_expired_processor_claim() -> None:
    job = _pending_job(available_at=PAST)
    pub_token = uuid4()
    publishing = claim_for_publishing(
        job,
        claim_token=pub_token,
        worker_id="worker-a",
        now=PAST,
        expected_version=job.version,
    )
    published = mark_published(
        publishing,
        claim_token=pub_token,
        now=PAST,
        expected_version=publishing.version,
    )
    proc_token = uuid4()
    processing = claim_for_processing(
        published,
        claim_token=proc_token,
        worker_id="processor-a",
        now=PAST,
        expected_version=published.version,
    )
    recovered = recover_expired_processor_claim(processing, now=NOW)
    assert recovered.state is OutboxJobState.PUBLISHED
    assert recovered.processing_started_at is None


def test_recover_expired_publisher_claim_rejects_active_lease() -> None:
    job = _pending_job()
    publishing = claim_for_publishing(
        job,
        claim_token=uuid4(),
        worker_id="worker-a",
        now=NOW,
        expected_version=job.version,
    )
    with pytest.raises(OutboxTransitionError, match="claim has not expired"):
        recover_expired_publisher_claim(publishing, now=NOW)


def test_reference_tenant_mismatch_rejected() -> None:
    with pytest.raises(OutboxInvariantError, match="reference tenant_id must match"):
        build_outbox_job(
            job_id=uuid4(),
            tenant_id=TENANT_A,
            job_kind=OutboxJobKind.CONTENT_REDACT,
            reference=OutboxJobReference(
                tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
                resource_type="message",
                resource_id=RESOURCE_ID,
                schema_version=1,
            ),
            deduplication_key="content_redact_mismatch",
            created_at=NOW,
        )


def test_invalid_deduplication_key_rejected() -> None:
    with pytest.raises(OutboxInvariantError, match="deduplication_key format is invalid"):
        build_outbox_job(
            job_id=uuid4(),
            tenant_id=TENANT_A,
            job_kind=OutboxJobKind.CONTENT_REDACT,
            reference=_reference(),
            deduplication_key="INVALID KEY",
            created_at=NOW,
        )


def test_invalid_worker_id_rejected_on_claim() -> None:
    job = _pending_job()
    with pytest.raises(OutboxInvariantError, match="worker_id format is invalid"):
        claim_for_publishing(
            job,
            claim_token=uuid4(),
            worker_id="INVALID",
            now=NOW,
            expected_version=job.version,
        )


def test_schedule_retry_processor_resets_published_at() -> None:
    job = _pending_job()
    pub_token = uuid4()
    publishing = claim_for_publishing(
        job,
        claim_token=pub_token,
        worker_id="worker-a",
        now=NOW,
        expected_version=job.version,
    )
    published = mark_published(
        publishing,
        claim_token=pub_token,
        now=NOW,
        expected_version=publishing.version,
    )
    proc_token = uuid4()
    processing = claim_for_processing(
        published,
        claim_token=proc_token,
        worker_id="processor-a",
        now=NOW,
        expected_version=published.version,
    )
    retried = schedule_retry(
        processing,
        claim_token=proc_token,
        phase=OutboxJobPhase.PROCESSOR,
        error_code=OutboxErrorCode.HANDLER_FAILED,
        now=NOW,
        expected_version=processing.version,
    )
    assert retried.state is OutboxJobState.RETRY_SCHEDULED
    assert retried.published_at is None


def test_mark_published_rejects_pending_state() -> None:
    job = _pending_job()
    with pytest.raises(OutboxTransitionError, match="not in publishing state"):
        mark_published(
            job,
            claim_token=uuid4(),
            now=NOW,
            expected_version=job.version,
        )
