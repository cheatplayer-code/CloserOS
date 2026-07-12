"""Read-model queries for RSTU conversation list, attribution, and aggregates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.manager_attribution import (
    attribute_threads_to_managers,
    thread_ids_for_manager,
)
from closeros.application.metrics_source_data import MetricsAssignmentRow, MetricsThreadRow
from closeros.infrastructure.analysis_orm import (
    ConversationAnalysisRunRow,
    ConversationFindingRow,
)
from closeros.infrastructure.canonical_orm import (
    ChannelConnectionRow,
    ConversationThreadRow,
    ManagerAssignmentRow,
    MessageDeletionEventRow,
    MessageDeliveryStatusEventRow,
    MessageEditEventRow,
    MessageRow,
)
from closeros.infrastructure.cursor_pagination import KeysetCursor, KeysetPage, apply_keyset_cursor
from closeros.infrastructure.follow_up_task_orm import FollowUpTaskRow


@dataclass(frozen=True, slots=True)
class ConversationListFilter:
    tenant_id: UUID
    attribution_as_of: datetime
    updated_after: datetime | None = None
    updated_before: datetime | None = None
    provider: str | None = None
    manager_user_id: UUID | None = None
    lifecycle_status: str | None = None
    finding_severity: str | None = None
    finding_code: str | None = None
    has_unresolved_task: bool | None = None


@dataclass(frozen=True, slots=True)
class ConversationListItem:
    id: UUID
    tenant_id: UUID
    channel_connection_id: UUID
    provider: str
    external_conversation_id: str
    lifecycle_status: str | None
    manager_user_id: UUID | None
    updated_at: datetime
    open_finding_count: int
    high_severity_finding_count: int
    has_unresolved_task: bool


@dataclass(frozen=True, slots=True)
class FindingCountByCode:
    finding_code: str
    severity: str
    count: int


@dataclass(frozen=True, slots=True)
class ManagerTaskCounts:
    open_count: int
    in_progress_count: int
    overdue_count: int
    completed_count: int
    cancelled_count: int


class ProductQueryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_attribution(
        self,
        *,
        tenant_id: UUID,
        window_end: datetime,
    ) -> dict[UUID, UUID]:
        threads = await self._load_all_threads(tenant_id=tenant_id)
        assignments = await self._load_assignments(tenant_id=tenant_id, window_end=window_end)
        return attribute_threads_to_managers(
            threads=threads,
            assignments=assignments,
            window_end=window_end,
        )

    async def list_conversations(
        self,
        *,
        filters: ConversationListFilter,
        manager_scope_user_id: UUID | None,
        limit: int,
        cursor: KeysetCursor | None,
    ) -> KeysetPage[ConversationListItem]:
        attribution = await self.load_attribution(
            tenant_id=filters.tenant_id,
            window_end=filters.attribution_as_of,
        )
        allowed_thread_ids: frozenset[UUID] | None = None
        if manager_scope_user_id is not None:
            allowed_thread_ids = thread_ids_for_manager(
                attributed=attribution,
                manager_user_id=manager_scope_user_id,
            )
        elif filters.manager_user_id is not None:
            allowed_thread_ids = thread_ids_for_manager(
                attributed=attribution,
                manager_user_id=filters.manager_user_id,
            )

        statement = (
            select(ConversationThreadRow, ChannelConnectionRow.provider)
            .join(
                ChannelConnectionRow,
                and_(
                    ChannelConnectionRow.tenant_id == ConversationThreadRow.tenant_id,
                    ChannelConnectionRow.id == ConversationThreadRow.channel_connection_id,
                ),
            )
            .where(ConversationThreadRow.tenant_id == filters.tenant_id)
        )
        if allowed_thread_ids is not None:
            if not allowed_thread_ids:
                return KeysetPage(items=(), next_cursor=None)
            statement = statement.where(ConversationThreadRow.id.in_(allowed_thread_ids))
        if filters.updated_after is not None:
            statement = statement.where(ConversationThreadRow.updated_at >= filters.updated_after)
        if filters.updated_before is not None:
            statement = statement.where(ConversationThreadRow.updated_at < filters.updated_before)
        if filters.provider is not None:
            statement = statement.where(ChannelConnectionRow.provider == filters.provider)
        if filters.lifecycle_status is not None:
            statement = statement.where(
                ConversationThreadRow.lifecycle_status == filters.lifecycle_status
            )
        if filters.finding_severity is not None or filters.finding_code is not None:
            finding_conditions = [
                ConversationFindingRow.tenant_id == filters.tenant_id,
                ConversationFindingRow.status == "open",
                ConversationFindingRow.analysis_run_id.in_(
                    select(ConversationAnalysisRunRow.id).where(
                        ConversationAnalysisRunRow.tenant_id == filters.tenant_id,
                        ConversationAnalysisRunRow.conversation_thread_id
                        == ConversationThreadRow.id,
                    )
                ),
            ]
            if filters.finding_severity is not None:
                finding_conditions.append(
                    ConversationFindingRow.severity == filters.finding_severity
                )
            if filters.finding_code is not None:
                finding_conditions.append(
                    ConversationFindingRow.finding_code == filters.finding_code
                )
            statement = statement.where(
                exists(select(ConversationFindingRow.id).where(*finding_conditions))
            )
        if filters.has_unresolved_task is True:
            statement = statement.where(self._unresolved_task_exists(filters.tenant_id))
        elif filters.has_unresolved_task is False:
            statement = statement.where(~self._unresolved_task_exists(filters.tenant_id))

        statement = apply_keyset_cursor(
            statement,
            occurred_at=cast(ColumnElement[datetime], ConversationThreadRow.updated_at),
            row_id=cast(ColumnElement[UUID], ConversationThreadRow.id),
            cursor=cursor,
            descending=True,
        )
        statement = statement.order_by(
            ConversationThreadRow.updated_at.desc(),
            ConversationThreadRow.id.desc(),
        ).limit(limit + 1)
        rows = (await self._session.execute(statement)).all()
        page_thread_ids = tuple(row[0].id for row in rows[:limit])
        finding_counts = await self._batch_finding_counts(
            tenant_id=filters.tenant_id,
            thread_ids=page_thread_ids,
        )
        unresolved = await self._batch_unresolved_tasks(
            tenant_id=filters.tenant_id,
            thread_ids=page_thread_ids,
        )
        items: list[ConversationListItem] = []
        for thread_row, provider in rows[:limit]:
            open_count, high_count = finding_counts.get(thread_row.id, (0, 0))
            items.append(
                ConversationListItem(
                    id=thread_row.id,
                    tenant_id=thread_row.tenant_id,
                    channel_connection_id=thread_row.channel_connection_id,
                    provider=provider,
                    external_conversation_id=thread_row.external_conversation_id,
                    lifecycle_status=thread_row.lifecycle_status,
                    manager_user_id=attribution.get(thread_row.id),
                    updated_at=thread_row.updated_at,
                    open_finding_count=open_count,
                    high_severity_finding_count=high_count,
                    has_unresolved_task=unresolved.get(thread_row.id, False),
                )
            )
        next_cursor = None
        if len(rows) > limit:
            last_thread = rows[limit - 1][0]
            next_cursor = KeysetCursor(occurred_at=last_thread.updated_at, row_id=last_thread.id)
        return KeysetPage(items=tuple(items), next_cursor=next_cursor)

    async def latest_message_id_for_thread(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID,
    ) -> UUID | None:
        statement = (
            select(MessageRow.id)
            .where(
                MessageRow.tenant_id == tenant_id,
                MessageRow.conversation_thread_id == conversation_thread_id,
            )
            .order_by(MessageRow.received_at.desc(), MessageRow.id.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def count_open_findings_for_threads(
        self,
        *,
        tenant_id: UUID,
        thread_ids: frozenset[UUID],
        severity: str | None = None,
    ) -> int:
        if not thread_ids:
            return 0
        conditions = [
            ConversationFindingRow.tenant_id == tenant_id,
            ConversationFindingRow.status == "open",
            ConversationAnalysisRunRow.tenant_id == tenant_id,
            ConversationAnalysisRunRow.conversation_thread_id.in_(thread_ids),
        ]
        if severity is not None:
            conditions.append(ConversationFindingRow.severity == severity)
        statement = (
            select(func.count())
            .select_from(ConversationFindingRow)
            .join(
                ConversationAnalysisRunRow,
                ConversationFindingRow.analysis_run_id == ConversationAnalysisRunRow.id,
            )
            .where(*conditions)
        )
        if severity == "high_critical":
            statement = (
                select(func.count())
                .select_from(ConversationFindingRow)
                .join(
                    ConversationAnalysisRunRow,
                    ConversationFindingRow.analysis_run_id == ConversationAnalysisRunRow.id,
                )
                .where(
                    ConversationFindingRow.tenant_id == tenant_id,
                    ConversationFindingRow.status == "open",
                    ConversationFindingRow.severity.in_(("high", "critical")),
                    ConversationAnalysisRunRow.tenant_id == tenant_id,
                    ConversationAnalysisRunRow.conversation_thread_id.in_(thread_ids),
                )
            )
        return int((await self._session.execute(statement)).scalar_one())

    async def finding_counts_by_code_for_manager_threads(
        self,
        *,
        tenant_id: UUID,
        thread_ids: frozenset[UUID],
    ) -> tuple[FindingCountByCode, ...]:
        if not thread_ids:
            return ()
        statement = (
            select(
                ConversationFindingRow.finding_code,
                ConversationFindingRow.severity,
                func.count(),
            )
            .join(
                ConversationAnalysisRunRow,
                ConversationFindingRow.analysis_run_id == ConversationAnalysisRunRow.id,
            )
            .where(
                ConversationFindingRow.tenant_id == tenant_id,
                ConversationFindingRow.status == "open",
                ConversationAnalysisRunRow.tenant_id == tenant_id,
                ConversationAnalysisRunRow.conversation_thread_id.in_(thread_ids),
            )
            .group_by(ConversationFindingRow.finding_code, ConversationFindingRow.severity)
        )
        rows = (await self._session.execute(statement)).all()
        return tuple(
            FindingCountByCode(finding_code=code, severity=severity, count=int(count))
            for code, severity, count in rows
        )

    async def task_counts_for_membership(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        now: datetime,
    ) -> ManagerTaskCounts:
        base = (
            select(FollowUpTaskRow.status, func.count())
            .where(
                FollowUpTaskRow.tenant_id == tenant_id,
                FollowUpTaskRow.assigned_membership_id == membership_id,
            )
            .group_by(FollowUpTaskRow.status)
        )
        counts = {"open": 0, "in_progress": 0, "completed": 0, "cancelled": 0}
        result = await self._session.execute(base)
        for status_value, count in result.all():
            counts[status_value] = int(count)
        overdue_statement = select(func.count()).where(
            FollowUpTaskRow.tenant_id == tenant_id,
            FollowUpTaskRow.assigned_membership_id == membership_id,
            FollowUpTaskRow.status.in_(("open", "in_progress")),
            FollowUpTaskRow.due_at.is_not(None),
            FollowUpTaskRow.due_at < now,
        )
        overdue = int((await self._session.execute(overdue_statement)).scalar_one())
        return ManagerTaskCounts(
            open_count=counts["open"],
            in_progress_count=counts["in_progress"],
            overdue_count=overdue,
            completed_count=counts["completed"],
            cancelled_count=counts["cancelled"],
        )

    async def list_thread_message_events(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID,
    ) -> tuple[object, ...]:
        edits = (
            (
                await self._session.execute(
                    select(MessageEditEventRow)
                    .join(MessageRow, MessageEditEventRow.message_id == MessageRow.id)
                    .where(
                        MessageEditEventRow.tenant_id == tenant_id,
                        MessageRow.conversation_thread_id == conversation_thread_id,
                    )
                    .order_by(MessageEditEventRow.occurred_at.asc(), MessageEditEventRow.id.asc())
                )
            )
            .scalars()
            .all()
        )
        deletions = (
            (
                await self._session.execute(
                    select(MessageDeletionEventRow)
                    .join(MessageRow, MessageDeletionEventRow.message_id == MessageRow.id)
                    .where(
                        MessageDeletionEventRow.tenant_id == tenant_id,
                        MessageRow.conversation_thread_id == conversation_thread_id,
                    )
                    .order_by(
                        MessageDeletionEventRow.occurred_at.asc(), MessageDeletionEventRow.id.asc()
                    )
                )
            )
            .scalars()
            .all()
        )
        deliveries = (
            (
                await self._session.execute(
                    select(MessageDeliveryStatusEventRow)
                    .join(MessageRow, MessageDeliveryStatusEventRow.message_id == MessageRow.id)
                    .where(
                        MessageDeliveryStatusEventRow.tenant_id == tenant_id,
                        MessageRow.conversation_thread_id == conversation_thread_id,
                    )
                    .order_by(
                        MessageDeliveryStatusEventRow.occurred_at.asc(),
                        MessageDeliveryStatusEventRow.id.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        return (*edits, *deletions, *deliveries)

    def _unresolved_task_exists(self, tenant_id: UUID) -> ColumnElement[bool]:
        return exists(
            select(FollowUpTaskRow.id).where(
                FollowUpTaskRow.tenant_id == tenant_id,
                FollowUpTaskRow.conversation_thread_id == ConversationThreadRow.id,
                FollowUpTaskRow.status.in_(("open", "in_progress")),
            )
        )

    async def _batch_finding_counts(
        self,
        *,
        tenant_id: UUID,
        thread_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[int, int]]:
        if not thread_ids:
            return {}
        statement = (
            select(
                ConversationAnalysisRunRow.conversation_thread_id,
                func.count(),
                func.count().filter(
                    ConversationFindingRow.severity.in_(("high", "critical")),
                ),
            )
            .join(
                ConversationFindingRow,
                ConversationFindingRow.analysis_run_id == ConversationAnalysisRunRow.id,
            )
            .where(
                ConversationAnalysisRunRow.tenant_id == tenant_id,
                ConversationFindingRow.tenant_id == tenant_id,
                ConversationFindingRow.status == "open",
                ConversationAnalysisRunRow.conversation_thread_id.in_(thread_ids),
            )
            .group_by(ConversationAnalysisRunRow.conversation_thread_id)
        )
        result = await self._session.execute(statement)
        return {row[0]: (int(row[1]), int(row[2])) for row in result.all()}

    async def _batch_unresolved_tasks(
        self,
        *,
        tenant_id: UUID,
        thread_ids: tuple[UUID, ...],
    ) -> dict[UUID, bool]:
        if not thread_ids:
            return {}
        statement = (
            select(FollowUpTaskRow.conversation_thread_id, func.count())
            .where(
                FollowUpTaskRow.tenant_id == tenant_id,
                FollowUpTaskRow.conversation_thread_id.in_(thread_ids),
                FollowUpTaskRow.status.in_(("open", "in_progress")),
            )
            .group_by(FollowUpTaskRow.conversation_thread_id)
        )
        result = await self._session.execute(statement)
        return {row[0]: int(row[1]) > 0 for row in result.all()}

    async def _load_all_threads(self, *, tenant_id: UUID) -> tuple[MetricsThreadRow, ...]:
        result = await self._session.execute(
            select(ConversationThreadRow).where(ConversationThreadRow.tenant_id == tenant_id)
        )
        return tuple(
            MetricsThreadRow(id=row.id, tenant_id=row.tenant_id, sales_case_id=row.sales_case_id)
            for row in result.scalars().all()
        )

    async def _load_assignments(
        self,
        *,
        tenant_id: UUID,
        window_end: datetime,
    ) -> tuple[MetricsAssignmentRow, ...]:
        result = await self._session.execute(
            select(ManagerAssignmentRow).where(
                ManagerAssignmentRow.tenant_id == tenant_id,
                ManagerAssignmentRow.assigned_at <= window_end,
            )
        )
        return tuple(
            MetricsAssignmentRow(
                id=row.id,
                tenant_id=row.tenant_id,
                manager_user_id=row.manager_user_id,
                conversation_thread_id=row.conversation_thread_id,
                sales_case_id=row.sales_case_id,
                assigned_at=row.assigned_at,
            )
            for row in result.scalars().all()
        )
