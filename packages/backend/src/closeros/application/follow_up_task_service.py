"""Application service for follow-up task lifecycle management."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.follow_up_task_persistence import (
    FollowUpTaskListFilter,
    FollowUpTaskNotFoundError,
    FollowUpTaskRecord,
    FollowUpTaskVersionConflictError,
)
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.product_audit import (
    follow_up_task_created_event,
    follow_up_task_mutated_event,
)
from closeros.domain.audit import AuditAction, AuditActorType
from closeros.domain.follow_up_task import (
    FollowUpTask,
    FollowUpTaskPriority,
    FollowUpTaskStatus,
    FollowUpTaskTransitionError,
    validate_follow_up_task_transition,
)
from closeros.infrastructure.cursor_pagination import KeysetCursor, KeysetPage

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]


class FollowUpTaskServiceError(Exception):
    """Raised when follow-up task operations cannot be completed."""


class FollowUpTaskAccessDeniedError(FollowUpTaskServiceError):
    """Raised when caller lacks permission for the operation."""


class FollowUpTaskService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        uuid_factory: _UuidFactory,
        clock: _Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._uuid_factory = uuid_factory
        self._clock = clock

    async def create_task(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID,
        title: str,
        priority: FollowUpTaskPriority,
        assigned_membership_id: UUID | None,
        source_finding_id: UUID | None,
        due_at: datetime | None,
        created_by_user_id: UUID,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> FollowUpTask:
        now = self._clock()
        task = FollowUpTask(
            id=self._uuid_factory(),
            tenant_id=tenant_id,
            conversation_thread_id=conversation_thread_id,
            source_finding_id=source_finding_id,
            title=title,
            status=FollowUpTaskStatus.OPEN,
            priority=priority,
            assigned_membership_id=assigned_membership_id,
            created_by_user_id=created_by_user_id,
            due_at=due_at,
            completed_at=None,
            cancelled_at=None,
            created_at=now,
            updated_at=now,
            version=1,
        )
        uow = self._uow_factory()
        async with uow:
            thread = await uow.conversation_threads.get_by_id(
                tenant_id=tenant_id,
                thread_id=conversation_thread_id,
            )
            if thread is None:
                raise FollowUpTaskServiceError("conversation unavailable")
            await uow.follow_up_tasks.add(record=_record_from_domain(task))
            await append_required_audit_event(
                uow.audit_events,
                follow_up_task_created_event(
                    tenant_id=tenant_id,
                    task_id=task.id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
        return task

    async def mutate_status(
        self,
        *,
        tenant_id: UUID,
        task_id: UUID,
        target_status: FollowUpTaskStatus,
        audit_action: AuditAction,
        expected_version: int,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> FollowUpTask:
        now = self._clock()
        uow = self._uow_factory()
        async with uow:
            current = await uow.follow_up_tasks.get_by_id_for_update(
                tenant_id=tenant_id,
                task_id=task_id,
            )
            if current is None:
                raise FollowUpTaskNotFoundError("follow-up task not found")
            domain = _domain_from_record(current)
            try:
                validate_follow_up_task_transition(current=domain.status, target=target_status)
            except FollowUpTaskTransitionError as error:
                raise FollowUpTaskServiceError("operation unavailable") from error
            completed_at = domain.completed_at
            cancelled_at = domain.cancelled_at
            if target_status is FollowUpTaskStatus.COMPLETED:
                completed_at = now
                cancelled_at = None
            elif target_status is FollowUpTaskStatus.CANCELLED:
                cancelled_at = now
                completed_at = None
            else:
                completed_at = None
                cancelled_at = None
            updated = replace(
                domain,
                status=target_status,
                completed_at=completed_at,
                cancelled_at=cancelled_at,
                updated_at=now,
                version=domain.version + 1,
            )
            FollowUpTask(
                id=updated.id,
                tenant_id=updated.tenant_id,
                conversation_thread_id=updated.conversation_thread_id,
                source_finding_id=updated.source_finding_id,
                title=updated.title,
                status=updated.status,
                priority=updated.priority,
                assigned_membership_id=updated.assigned_membership_id,
                created_by_user_id=updated.created_by_user_id,
                due_at=updated.due_at,
                completed_at=updated.completed_at,
                cancelled_at=updated.cancelled_at,
                created_at=updated.created_at,
                updated_at=updated.updated_at,
                version=updated.version,
            )
            try:
                persisted = await uow.follow_up_tasks.update(
                    record=_record_from_domain(updated),
                    expected_version=expected_version,
                )
            except FollowUpTaskVersionConflictError as error:
                raise FollowUpTaskServiceError("operation unavailable") from error
            await append_required_audit_event(
                uow.audit_events,
                follow_up_task_mutated_event(
                    action=audit_action,
                    tenant_id=tenant_id,
                    task_id=task_id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                    outcome=target_status.value,
                ),
            )
            await uow.commit()
        return _domain_from_record(persisted)

    async def assign(
        self,
        *,
        tenant_id: UUID,
        task_id: UUID,
        assigned_membership_id: UUID | None,
        expected_version: int,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> FollowUpTask:
        return await self._update_fields(
            tenant_id=tenant_id,
            task_id=task_id,
            expected_version=expected_version,
            audit_action=AuditAction.FOLLOW_UP_TASK_ASSIGNED,
            audit_context=audit_context,
            actor_type=actor_type,
            actor_id=actor_id,
            mutator=lambda task: replace(task, assigned_membership_id=assigned_membership_id),
        )

    async def change_priority(
        self,
        *,
        tenant_id: UUID,
        task_id: UUID,
        priority: FollowUpTaskPriority,
        expected_version: int,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> FollowUpTask:
        return await self._update_fields(
            tenant_id=tenant_id,
            task_id=task_id,
            expected_version=expected_version,
            audit_action=AuditAction.FOLLOW_UP_TASK_PRIORITY_CHANGED,
            audit_context=audit_context,
            actor_type=actor_type,
            actor_id=actor_id,
            mutator=lambda task: replace(task, priority=priority),
        )

    async def change_due_date(
        self,
        *,
        tenant_id: UUID,
        task_id: UUID,
        due_at: datetime | None,
        expected_version: int,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> FollowUpTask:
        return await self._update_fields(
            tenant_id=tenant_id,
            task_id=task_id,
            expected_version=expected_version,
            audit_action=AuditAction.FOLLOW_UP_TASK_DUE_DATE_CHANGED,
            audit_context=audit_context,
            actor_type=actor_type,
            actor_id=actor_id,
            mutator=lambda task: replace(task, due_at=due_at),
        )

    async def list_tasks(
        self,
        *,
        filters: FollowUpTaskListFilter,
        limit: int,
        cursor: KeysetCursor | None,
    ) -> KeysetPage[FollowUpTask]:
        uow = self._uow_factory()
        async with uow:
            page = await uow.follow_up_tasks.list_page(
                filters=filters,
                limit=limit,
                cursor=cursor,
            )
        return KeysetPage(
            items=tuple(_domain_from_record(item) for item in page.items),
            next_cursor=page.next_cursor,
        )

    async def get_task(self, *, tenant_id: UUID, task_id: UUID) -> FollowUpTask | None:
        uow = self._uow_factory()
        async with uow:
            record = await uow.follow_up_tasks.get_by_id(tenant_id=tenant_id, task_id=task_id)
        return None if record is None else _domain_from_record(record)

    async def _update_fields(
        self,
        *,
        tenant_id: UUID,
        task_id: UUID,
        expected_version: int,
        audit_action: AuditAction,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
        mutator: Callable[[FollowUpTask], FollowUpTask],
    ) -> FollowUpTask:
        now = self._clock()
        uow = self._uow_factory()
        async with uow:
            current = await uow.follow_up_tasks.get_by_id_for_update(
                tenant_id=tenant_id,
                task_id=task_id,
            )
            if current is None:
                raise FollowUpTaskNotFoundError("follow-up task not found")
            updated = replace(
                mutator(_domain_from_record(current)),
                updated_at=now,
                version=current.version + 1,
            )
            FollowUpTask(
                id=updated.id,
                tenant_id=updated.tenant_id,
                conversation_thread_id=updated.conversation_thread_id,
                source_finding_id=updated.source_finding_id,
                title=updated.title,
                status=updated.status,
                priority=updated.priority,
                assigned_membership_id=updated.assigned_membership_id,
                created_by_user_id=updated.created_by_user_id,
                due_at=updated.due_at,
                completed_at=updated.completed_at,
                cancelled_at=updated.cancelled_at,
                created_at=updated.created_at,
                updated_at=updated.updated_at,
                version=updated.version,
            )
            try:
                persisted = await uow.follow_up_tasks.update(
                    record=_record_from_domain(updated),
                    expected_version=expected_version,
                )
            except FollowUpTaskVersionConflictError as error:
                raise FollowUpTaskServiceError("operation unavailable") from error
            await append_required_audit_event(
                uow.audit_events,
                follow_up_task_mutated_event(
                    action=audit_action,
                    tenant_id=tenant_id,
                    task_id=task_id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                    outcome="updated",
                ),
            )
            await uow.commit()
        return _domain_from_record(persisted)


def _record_from_domain(task: FollowUpTask) -> FollowUpTaskRecord:
    return FollowUpTaskRecord(
        id=task.id,
        tenant_id=task.tenant_id,
        conversation_thread_id=task.conversation_thread_id,
        source_finding_id=task.source_finding_id,
        title=task.title,
        status=task.status,
        priority=task.priority,
        assigned_membership_id=task.assigned_membership_id,
        created_by_user_id=task.created_by_user_id,
        due_at=task.due_at,
        completed_at=task.completed_at,
        cancelled_at=task.cancelled_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        version=task.version,
    )


def _domain_from_record(record: FollowUpTaskRecord) -> FollowUpTask:
    return FollowUpTask(
        id=record.id,
        tenant_id=record.tenant_id,
        conversation_thread_id=record.conversation_thread_id,
        source_finding_id=record.source_finding_id,
        title=record.title,
        status=record.status,
        priority=record.priority,
        assigned_membership_id=record.assigned_membership_id,
        created_by_user_id=record.created_by_user_id,
        due_at=record.due_at,
        completed_at=record.completed_at,
        cancelled_at=record.cancelled_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        version=record.version,
    )
