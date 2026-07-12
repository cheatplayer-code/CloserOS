"""PostgreSQL repository for follow-up tasks."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.follow_up_task_persistence import (
    FollowUpTaskCounts,
    FollowUpTaskListFilter,
    FollowUpTaskPersistenceError,
    FollowUpTaskRecord,
    FollowUpTaskVersionConflictError,
)
from closeros.domain.follow_up_task import FollowUpTaskStatus
from closeros.infrastructure import follow_up_task_mappers as mappers
from closeros.infrastructure.cursor_pagination import KeysetCursor, KeysetPage, apply_keyset_cursor
from closeros.infrastructure.follow_up_task_orm import FollowUpTaskRow
from closeros.infrastructure.persistence_errors import translate_integrity_error
from closeros.infrastructure.repository_helpers import tenant_scoped_get

_UNRESOLVED_STATUSES = (
    FollowUpTaskStatus.OPEN.value,
    FollowUpTaskStatus.IN_PROGRESS.value,
)


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise translate_integrity_error(
            error,
            constraint_errors={},
            default=FollowUpTaskPersistenceError,
            message="follow-up task persistence integrity error",
        ) from error


class SqlAlchemyFollowUpTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, record: FollowUpTaskRecord) -> None:
        self._session.add(mappers.record_to_row(record))
        await _flush(self._session)

    async def get_by_id(self, *, tenant_id: UUID, task_id: UUID) -> FollowUpTaskRecord | None:
        row = await tenant_scoped_get(
            self._session,
            FollowUpTaskRow,
            tenant_id=tenant_id,
            record_id=task_id,
        )
        return None if row is None else mappers.row_to_record(row)

    async def get_by_id_for_update(
        self,
        *,
        tenant_id: UUID,
        task_id: UUID,
    ) -> FollowUpTaskRecord | None:
        statement = (
            select(FollowUpTaskRow)
            .where(
                FollowUpTaskRow.tenant_id == tenant_id,
                FollowUpTaskRow.id == task_id,
            )
            .with_for_update()
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.row_to_record(row)

    async def update(
        self, *, record: FollowUpTaskRecord, expected_version: int
    ) -> FollowUpTaskRecord:
        row = (
            await self._session.execute(
                select(FollowUpTaskRow)
                .where(
                    FollowUpTaskRow.tenant_id == record.tenant_id,
                    FollowUpTaskRow.id == record.id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise FollowUpTaskPersistenceError("follow-up task not found")
        if row.version != expected_version:
            raise FollowUpTaskVersionConflictError("follow-up task version conflict")
        row.title = record.title
        row.status = record.status.value
        row.priority = record.priority.value
        row.assigned_membership_id = record.assigned_membership_id
        row.due_at = record.due_at
        row.completed_at = record.completed_at
        row.cancelled_at = record.cancelled_at
        row.updated_at = record.updated_at
        row.version = record.version
        await _flush(self._session)
        return mappers.row_to_record(row)

    async def list_page(
        self,
        *,
        filters: FollowUpTaskListFilter,
        limit: int,
        cursor: KeysetCursor | None,
    ) -> KeysetPage[FollowUpTaskRecord]:
        statement = select(FollowUpTaskRow).where(FollowUpTaskRow.tenant_id == filters.tenant_id)
        if filters.status is not None:
            statement = statement.where(FollowUpTaskRow.status == filters.status.value)
        if filters.assigned_membership_id is not None:
            statement = statement.where(
                FollowUpTaskRow.assigned_membership_id == filters.assigned_membership_id
            )
        if filters.conversation_thread_id is not None:
            statement = statement.where(
                FollowUpTaskRow.conversation_thread_id == filters.conversation_thread_id
            )
        if filters.due_before is not None:
            statement = statement.where(FollowUpTaskRow.due_at <= filters.due_before)
        if filters.due_after is not None:
            statement = statement.where(FollowUpTaskRow.due_at >= filters.due_after)
        if filters.overdue_only and filters.now is not None:
            statement = statement.where(
                FollowUpTaskRow.status.in_(_UNRESOLVED_STATUSES),
                FollowUpTaskRow.due_at.is_not(None),
                FollowUpTaskRow.due_at < filters.now,
            )
        statement = apply_keyset_cursor(
            statement,
            occurred_at=cast(ColumnElement[datetime], FollowUpTaskRow.updated_at),
            row_id=cast(ColumnElement[UUID], FollowUpTaskRow.id),
            cursor=cursor,
            descending=True,
        )
        statement = statement.order_by(
            FollowUpTaskRow.updated_at.desc(),
            FollowUpTaskRow.id.desc(),
        ).limit(limit + 1)
        rows = tuple((await self._session.execute(statement)).scalars().all())
        items = tuple(mappers.row_to_record(row) for row in rows[:limit])
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = KeysetCursor(occurred_at=last.updated_at, row_id=last.id)
        return KeysetPage(items=items, next_cursor=next_cursor)

    async def count_by_status(self, *, tenant_id: UUID, now: datetime) -> FollowUpTaskCounts:
        base = (
            select(FollowUpTaskRow.status, func.count())
            .where(FollowUpTaskRow.tenant_id == tenant_id)
            .group_by(FollowUpTaskRow.status)
        )
        counts = {status: 0 for status in FollowUpTaskStatus}
        result = await self._session.execute(base)
        for status_value, count in result.all():
            counts[FollowUpTaskStatus(status_value)] = int(count)
        overdue_statement = select(func.count()).where(
            FollowUpTaskRow.tenant_id == tenant_id,
            FollowUpTaskRow.status.in_(_UNRESOLVED_STATUSES),
            FollowUpTaskRow.due_at.is_not(None),
            FollowUpTaskRow.due_at < now,
        )
        overdue_count = int((await self._session.execute(overdue_statement)).scalar_one())
        return FollowUpTaskCounts(
            open_count=counts[FollowUpTaskStatus.OPEN],
            in_progress_count=counts[FollowUpTaskStatus.IN_PROGRESS],
            overdue_count=overdue_count,
            completed_count=counts[FollowUpTaskStatus.COMPLETED],
            cancelled_count=counts[FollowUpTaskStatus.CANCELLED],
        )

    async def has_unresolved_for_thread(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID,
    ) -> bool:
        statement = select(func.count()).where(
            FollowUpTaskRow.tenant_id == tenant_id,
            FollowUpTaskRow.conversation_thread_id == conversation_thread_id,
            FollowUpTaskRow.status.in_(_UNRESOLVED_STATUSES),
        )
        return int((await self._session.execute(statement)).scalar_one()) > 0
