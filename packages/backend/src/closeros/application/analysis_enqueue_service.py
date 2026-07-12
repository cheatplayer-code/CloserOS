"""Enqueue deduplicated `message.analyze` jobs after sanitization."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.outbox_persistence import DuplicateOutboxJobError
from closeros.domain.outbox import OutboxJobKind, OutboxJobReference, build_outbox_job

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]


class AnalysisEnqueueUnavailableError(Exception):
    """Raised when analysis enqueue fails transiently."""


def analysis_deduplication_key(*, message_id: UUID) -> str:
    return f"message_analyze_{message_id}"


class AnalysisEnqueueService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        uuid_factory: _UuidFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._uuid_factory = uuid_factory

    async def enqueue_after_sanitization(
        self,
        *,
        tenant_id: UUID,
        source_resource_type: str,
        source_resource_id: UUID,
        requested_at: datetime,
    ) -> UUID | None:
        uow = self._uow_factory()
        async with uow:
            policy = await uow.tenant_ai_policies.get_by_tenant_id(tenant_id=tenant_id)
            if policy is None or policy.mode == "off":
                return None

            message_id = await self._resolve_message_id(
                uow=uow,
                tenant_id=tenant_id,
                source_resource_type=source_resource_type,
                source_resource_id=source_resource_id,
            )
            if message_id is None:
                return None

            job_id = self._uuid_factory()
            try:
                await uow.outbox_jobs.enqueue(
                    build_outbox_job(
                        job_id=job_id,
                        tenant_id=tenant_id,
                        job_kind=OutboxJobKind.MESSAGE_ANALYZE,
                        reference=OutboxJobReference(
                            resource_type="message",
                            resource_id=message_id,
                            schema_version=1,
                            tenant_id=tenant_id,
                        ),
                        deduplication_key=analysis_deduplication_key(message_id=message_id),
                        created_at=requested_at,
                    )
                )
                await uow.commit()
                return job_id
            except DuplicateOutboxJobError:
                await uow.rollback()
                return job_id
            except Exception as error:
                await uow.rollback()
                raise AnalysisEnqueueUnavailableError("analysis enqueue failed") from error

    async def _resolve_message_id(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        source_resource_type: str,
        source_resource_id: UUID,
    ) -> UUID | None:
        if source_resource_type == "message":
            message = await uow.messages.get_by_id(
                tenant_id=tenant_id,
                message_id=source_resource_id,
            )
            return None if message is None else message.id
        if source_resource_type == "message_edit_event":
            edit_event = await uow.message_edit_events.get_by_id(
                tenant_id=tenant_id,
                event_id=source_resource_id,
            )
            return None if edit_event is None else edit_event.message_id
        return None
