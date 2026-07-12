"""Load canonical metadata required for deterministic metrics."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.metrics_source_data import (
    MetricsAssignmentRow,
    MetricsCrmOutcomeRow,
    MetricsDeliveryEventRow,
    MetricsMessageRow,
    MetricsSalesCaseRow,
    MetricsSourceData,
    MetricsThreadRow,
)
from closeros.domain.canonical_enums import (
    CrmOutcomeType,
    DeliveryStatus,
    MessageDirection,
    ParticipantSenderType,
    SalesCaseStatus,
)
from closeros.infrastructure.canonical_orm import (
    ConversationThreadRow,
    CRMOutcomeRow,
    ManagerAssignmentRow,
    MessageDeliveryStatusEventRow,
    MessageRow,
    SalesCaseRow,
)


class SqlAlchemyMetricsSourceLoader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_for_window(
        self,
        *,
        tenant_id: UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> MetricsSourceData:
        messages = await self._load_messages(
            tenant_id=tenant_id,
            window_start=window_start,
            window_end=window_end,
        )
        thread_ids = {message.conversation_thread_id for message in messages}
        threads = await self._load_threads(tenant_id=tenant_id, thread_ids=thread_ids)
        sales_case_ids = {
            thread.sales_case_id for thread in threads if thread.sales_case_id is not None
        }
        delivery_events = await self._load_delivery_events(
            tenant_id=tenant_id,
            window_start=window_start,
            window_end=window_end,
        )
        sales_cases = await self._load_sales_cases(
            tenant_id=tenant_id,
            window_start=window_start,
            window_end=window_end,
        )
        crm_outcomes = await self._load_crm_outcomes(
            tenant_id=tenant_id,
            sales_case_ids=sales_case_ids,
            window_start=window_start,
            window_end=window_end,
        )
        assignments = await self._load_assignments(tenant_id=tenant_id, window_end=window_end)
        watermark = window_end
        for collection in (messages, delivery_events, sales_cases, crm_outcomes, assignments):
            for item in collection:
                timestamp = _timestamp_for_watermark(item)
                if timestamp > watermark:
                    watermark = timestamp
        return MetricsSourceData(
            messages=messages,
            threads=threads,
            delivery_events=delivery_events,
            sales_cases=sales_cases,
            crm_outcomes=crm_outcomes,
            assignments=assignments,
            watermark=watermark,
        )

    async def _load_messages(
        self,
        *,
        tenant_id: UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[MetricsMessageRow, ...]:
        statement = select(MessageRow).where(
            MessageRow.tenant_id == tenant_id,
            MessageRow.received_at >= window_start,
            MessageRow.received_at < window_end,
        )
        result = await self._session.execute(statement)
        return tuple(
            MetricsMessageRow(
                id=row.id,
                tenant_id=row.tenant_id,
                conversation_thread_id=row.conversation_thread_id,
                sender_type=ParticipantSenderType(row.sender_type),
                direction=MessageDirection(row.direction),
                received_at=row.received_at,
            )
            for row in result.scalars().all()
        )

    async def _load_threads(
        self,
        *,
        tenant_id: UUID,
        thread_ids: set[UUID],
    ) -> tuple[MetricsThreadRow, ...]:
        if not thread_ids:
            return ()
        statement = select(ConversationThreadRow).where(
            ConversationThreadRow.tenant_id == tenant_id,
            ConversationThreadRow.id.in_(thread_ids),
        )
        result = await self._session.execute(statement)
        return tuple(
            MetricsThreadRow(
                id=row.id,
                tenant_id=row.tenant_id,
                sales_case_id=row.sales_case_id,
            )
            for row in result.scalars().all()
        )

    async def _load_delivery_events(
        self,
        *,
        tenant_id: UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[MetricsDeliveryEventRow, ...]:
        statement = (
            select(MessageDeliveryStatusEventRow, MessageRow.conversation_thread_id)
            .join(
                MessageRow,
                (MessageDeliveryStatusEventRow.tenant_id == MessageRow.tenant_id)
                & (MessageDeliveryStatusEventRow.message_id == MessageRow.id),
            )
            .where(
                MessageDeliveryStatusEventRow.tenant_id == tenant_id,
                MessageDeliveryStatusEventRow.occurred_at >= window_start,
                MessageDeliveryStatusEventRow.occurred_at < window_end,
            )
        )
        result = await self._session.execute(statement)
        return tuple(
            MetricsDeliveryEventRow(
                conversation_thread_id=thread_id,
                message_id=event.message_id,
                status=DeliveryStatus(event.status),
                occurred_at=event.occurred_at,
            )
            for event, thread_id in result.all()
        )

    async def _load_sales_cases(
        self,
        *,
        tenant_id: UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[MetricsSalesCaseRow, ...]:
        statement = select(SalesCaseRow).where(
            SalesCaseRow.tenant_id == tenant_id,
            SalesCaseRow.updated_at >= window_start,
            SalesCaseRow.updated_at < window_end,
        )
        result = await self._session.execute(statement)
        return tuple(
            MetricsSalesCaseRow(
                id=row.id,
                tenant_id=row.tenant_id,
                status=SalesCaseStatus(row.status),
                updated_at=row.updated_at,
            )
            for row in result.scalars().all()
        )

    async def _load_crm_outcomes(
        self,
        *,
        tenant_id: UUID,
        sales_case_ids: set[UUID],
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[MetricsCrmOutcomeRow, ...]:
        statement = select(CRMOutcomeRow).where(
            CRMOutcomeRow.tenant_id == tenant_id,
            CRMOutcomeRow.occurred_at >= window_start,
            CRMOutcomeRow.occurred_at < window_end,
        )
        if sales_case_ids:
            statement = statement.where(CRMOutcomeRow.sales_case_id.in_(sales_case_ids))
        result = await self._session.execute(statement)
        return tuple(
            MetricsCrmOutcomeRow(
                sales_case_id=row.sales_case_id,
                outcome_type=CrmOutcomeType(row.outcome_type),
                occurred_at=row.occurred_at,
            )
            for row in result.scalars().all()
        )

    async def _load_assignments(
        self,
        *,
        tenant_id: UUID,
        window_end: datetime,
    ) -> tuple[MetricsAssignmentRow, ...]:
        statement = select(ManagerAssignmentRow).where(
            ManagerAssignmentRow.tenant_id == tenant_id,
            ManagerAssignmentRow.assigned_at <= window_end,
        )
        result = await self._session.execute(statement)
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


def _timestamp_for_watermark(item: object) -> datetime:
    if hasattr(item, "received_at"):
        return item.received_at  # type: ignore[no-any-return]
    if hasattr(item, "occurred_at"):
        return item.occurred_at  # type: ignore[no-any-return]
    if hasattr(item, "updated_at"):
        return item.updated_at  # type: ignore[no-any-return]
    if hasattr(item, "assigned_at"):
        return item.assigned_at  # type: ignore[no-any-return]
    raise TypeError("unsupported watermark item")
