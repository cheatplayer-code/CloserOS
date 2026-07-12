"""Mappers between outbox domain entities and SQLAlchemy rows."""

from __future__ import annotations

from closeros.domain.outbox import (
    OutboxAttemptOutcome,
    OutboxErrorCode,
    OutboxJob,
    OutboxJobAttempt,
    OutboxJobKind,
    OutboxJobPhase,
    OutboxJobReference,
    OutboxJobState,
)
from closeros.infrastructure.outbox_orm import OutboxJobAttemptRow, OutboxJobRow


def outbox_job_to_row(job: OutboxJob) -> OutboxJobRow:
    return OutboxJobRow(
        id=job.id,
        tenant_id=job.tenant_id,
        job_kind=job.job_kind.value,
        resource_type=job.reference.resource_type,
        resource_id=job.reference.resource_id,
        secondary_resource_id=job.reference.secondary_id,
        schema_version=job.reference.schema_version,
        deduplication_key=job.deduplication_key,
        priority=job.priority,
        state=job.state.value,
        available_at=job.available_at,
        created_at=job.created_at,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        claim_token=job.claim_token,
        claimed_by=job.claimed_by,
        claimed_at=job.claimed_at,
        claim_expires_at=job.claim_expires_at,
        published_at=job.published_at,
        processing_started_at=job.processing_started_at,
        completed_at=job.completed_at,
        last_error_code=None if job.last_error_code is None else job.last_error_code.value,
        version=job.version,
    )


def outbox_job_to_domain(row: OutboxJobRow) -> OutboxJob:
    reference = OutboxJobReference(
        tenant_id=row.tenant_id,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        secondary_id=row.secondary_resource_id,
        schema_version=row.schema_version,
    )
    return OutboxJob(
        id=row.id,
        tenant_id=row.tenant_id,
        job_kind=OutboxJobKind(row.job_kind),
        reference=reference,
        deduplication_key=row.deduplication_key,
        priority=row.priority,
        state=OutboxJobState(row.state),
        available_at=row.available_at,
        created_at=row.created_at,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        version=row.version,
        claim_token=row.claim_token,
        claimed_by=row.claimed_by,
        claimed_at=row.claimed_at,
        claim_expires_at=row.claim_expires_at,
        published_at=row.published_at,
        processing_started_at=row.processing_started_at,
        completed_at=row.completed_at,
        last_error_code=None
        if row.last_error_code is None
        else OutboxErrorCode(row.last_error_code),
    )


def update_outbox_job_row(row: OutboxJobRow, job: OutboxJob) -> None:
    row.tenant_id = job.tenant_id
    row.job_kind = job.job_kind.value
    row.resource_type = job.reference.resource_type
    row.resource_id = job.reference.resource_id
    row.secondary_resource_id = job.reference.secondary_id
    row.schema_version = job.reference.schema_version
    row.deduplication_key = job.deduplication_key
    row.priority = job.priority
    row.state = job.state.value
    row.available_at = job.available_at
    row.created_at = job.created_at
    row.attempt_count = job.attempt_count
    row.max_attempts = job.max_attempts
    row.claim_token = job.claim_token
    row.claimed_by = job.claimed_by
    row.claimed_at = job.claimed_at
    row.claim_expires_at = job.claim_expires_at
    row.published_at = job.published_at
    row.processing_started_at = job.processing_started_at
    row.completed_at = job.completed_at
    row.last_error_code = None if job.last_error_code is None else job.last_error_code.value
    row.version = job.version


def outbox_job_attempt_to_row(attempt: OutboxJobAttempt) -> OutboxJobAttemptRow:
    return OutboxJobAttemptRow(
        id=attempt.id,
        job_id=attempt.job_id,
        attempt_number=attempt.attempt_number,
        phase=attempt.phase.value,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        outcome=attempt.outcome.value,
        error_code=None if attempt.error_code is None else attempt.error_code.value,
        claim_token=attempt.claim_token,
    )


def outbox_job_attempt_to_domain(row: OutboxJobAttemptRow) -> OutboxJobAttempt:
    return OutboxJobAttempt(
        id=row.id,
        job_id=row.job_id,
        attempt_number=row.attempt_number,
        phase=OutboxJobPhase(row.phase),
        started_at=row.started_at,
        finished_at=row.finished_at,
        outcome=OutboxAttemptOutcome(row.outcome),
        claim_token=row.claim_token,
        error_code=None if row.error_code is None else OutboxErrorCode(row.error_code),
    )
