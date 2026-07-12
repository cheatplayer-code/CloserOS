"""PostgreSQL append-only repository for audit events."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.audit_persistence import (
    AuditPersistenceError,
    AuditQueryCursor,
    AuditQueryFilter,
    AuditQueryPage,
)
from closeros.domain.audit import AuditEvent
from closeros.infrastructure import audit_mappers as mappers
from closeros.infrastructure.audit_orm import AuditEventRow


class SqlAlchemyAuditEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: AuditEvent) -> None:
        self._session.add(mappers.audit_event_to_row(event))
        try:
            await self._session.flush()
        except Exception as error:
            raise AuditPersistenceError("audit append failed") from error

    async def query_page(
        self,
        *,
        query_filter: AuditQueryFilter,
        cursor: AuditQueryCursor | None,
        page_size: int,
    ) -> AuditQueryPage:
        if page_size < 1:
            raise ValueError("page_size must be positive")

        statement = select(AuditEventRow).where(AuditEventRow.tenant_id == query_filter.tenant_id)

        if query_filter.action is not None:
            statement = statement.where(AuditEventRow.action == query_filter.action.value)

        if query_filter.actor_id is not None:
            statement = statement.where(AuditEventRow.actor_id == query_filter.actor_id)

        if query_filter.target_type is not None:
            statement = statement.where(AuditEventRow.target_type == query_filter.target_type.value)

        if query_filter.target_id is not None:
            statement = statement.where(AuditEventRow.target_id == query_filter.target_id)

        if query_filter.correlation_id is not None:
            statement = statement.where(AuditEventRow.correlation_id == query_filter.correlation_id)

        if query_filter.occurred_after is not None:
            statement = statement.where(AuditEventRow.occurred_at >= query_filter.occurred_after)

        if query_filter.occurred_before is not None:
            statement = statement.where(AuditEventRow.occurred_at <= query_filter.occurred_before)

        if cursor is not None:
            statement = statement.where(
                or_(
                    AuditEventRow.occurred_at < cursor.occurred_at,
                    and_(
                        AuditEventRow.occurred_at == cursor.occurred_at,
                        AuditEventRow.id < cursor.event_id,
                    ),
                )
            )

        statement = statement.order_by(
            AuditEventRow.occurred_at.desc(),
            AuditEventRow.id.desc(),
        ).limit(page_size + 1)

        result = await self._session.execute(statement)
        rows = result.scalars().all()

        has_more = len(rows) > page_size
        page_rows = rows[:page_size]
        events = tuple(mappers.audit_event_from_row(row) for row in page_rows)

        next_cursor: AuditQueryCursor | None = None
        if has_more and page_rows:
            last_row = page_rows[-1]
            next_cursor = AuditQueryCursor(
                occurred_at=last_row.occurred_at,
                event_id=last_row.id,
            )

        return AuditQueryPage(events=events, next_cursor=next_cursor)


def audit_event_row_values(event: AuditEvent) -> dict[str, Any]:
    """Expose row field values for tests without returning ORM instances."""

    row = mappers.audit_event_to_row(event)
    return {
        "id": row.id,
        "scope": row.scope,
        "tenant_id": row.tenant_id,
        "actor_type": row.actor_type,
        "actor_id": row.actor_id,
        "action": row.action,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "occurred_at": row.occurred_at,
        "correlation_id": row.correlation_id,
        "metadata": row.event_metadata,
    }
