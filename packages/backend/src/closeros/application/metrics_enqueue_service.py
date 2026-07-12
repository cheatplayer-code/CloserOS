"""Enqueue tenant metrics recalculation jobs idempotently."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.metrics_audit import metrics_recalculation_requested_event
from closeros.application.outbox_persistence import DuplicateOutboxJobError
from closeros.domain.audit import AuditActorType
from closeros.domain.metrics import METRIC_FORMULA_VERSION
from closeros.domain.outbox import OutboxJobKind, OutboxJobReference, build_outbox_job

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]


class MetricsEnqueueUnavailableError(Exception):
    """Raised when metrics job enqueue fails transiently."""


def metrics_deduplication_key(*, local_date: str) -> str:
    return f"metrics_recalc_{local_date}"


def local_calendar_date(*, occurred_at: datetime, time_zone: str) -> str:
    localized = occurred_at.astimezone(ZoneInfo(time_zone))
    return localized.date().isoformat()


class MetricsEnqueueService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        uuid_factory: _UuidFactory,
        service_actor_id: UUID,
    ) -> None:
        self._uow_factory = uow_factory
        self._uuid_factory = uuid_factory
        self._service_actor_id = service_actor_id

    async def enqueue_tenant_recalculation(
        self,
        *,
        tenant_id: UUID,
        time_zone: str,
        requested_at: datetime,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> UUID:
        local_date = local_calendar_date(occurred_at=requested_at, time_zone=time_zone)
        job_id = self._uuid_factory()
        audit_event_id = self._uuid_factory()
        uow = self._uow_factory()
        async with uow:
            try:
                await uow.outbox_jobs.enqueue(
                    build_outbox_job(
                        job_id=job_id,
                        tenant_id=tenant_id,
                        job_kind=OutboxJobKind.METRICS_RECALCULATE,
                        reference=OutboxJobReference(
                            resource_type="tenant",
                            resource_id=tenant_id,
                            schema_version=1,
                            tenant_id=tenant_id,
                        ),
                        deduplication_key=metrics_deduplication_key(local_date=local_date),
                        created_at=requested_at,
                    )
                )
                await append_required_audit_event(
                    uow.audit_events,
                    metrics_recalculation_requested_event(
                        tenant_id=tenant_id,
                        outbox_job_id=job_id,
                        formula_version=METRIC_FORMULA_VERSION,
                        window_code=f"daily_{local_date}",
                        occurred_at=requested_at,
                        audit_context=audit_context,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        event_id=audit_event_id,
                    ),
                )
                await uow.commit()
            except DuplicateOutboxJobError:
                await uow.rollback()
                return job_id
            except Exception as error:
                await uow.rollback()
                raise MetricsEnqueueUnavailableError("metrics enqueue failed") from error
        return job_id
