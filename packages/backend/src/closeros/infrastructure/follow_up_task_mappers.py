"""Mappers between follow-up task domain, records, and ORM rows."""

from __future__ import annotations

from closeros.application.follow_up_task_persistence import FollowUpTaskRecord
from closeros.domain.follow_up_task import FollowUpTask, FollowUpTaskPriority, FollowUpTaskStatus
from closeros.infrastructure.follow_up_task_orm import FollowUpTaskRow


def record_to_domain(record: FollowUpTaskRecord) -> FollowUpTask:
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


def domain_to_record(task: FollowUpTask) -> FollowUpTaskRecord:
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


def record_to_row(record: FollowUpTaskRecord) -> FollowUpTaskRow:
    return FollowUpTaskRow(
        id=record.id,
        tenant_id=record.tenant_id,
        conversation_thread_id=record.conversation_thread_id,
        source_finding_id=record.source_finding_id,
        title=record.title,
        status=record.status.value,
        priority=record.priority.value,
        assigned_membership_id=record.assigned_membership_id,
        created_by_user_id=record.created_by_user_id,
        due_at=record.due_at,
        completed_at=record.completed_at,
        cancelled_at=record.cancelled_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        version=record.version,
    )


def row_to_record(row: FollowUpTaskRow) -> FollowUpTaskRecord:
    return FollowUpTaskRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_thread_id=row.conversation_thread_id,
        source_finding_id=row.source_finding_id,
        title=row.title,
        status=FollowUpTaskStatus(row.status),
        priority=FollowUpTaskPriority(row.priority),
        assigned_membership_id=row.assigned_membership_id,
        created_by_user_id=row.created_by_user_id,
        due_at=row.due_at,
        completed_at=row.completed_at,
        cancelled_at=row.cancelled_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )
