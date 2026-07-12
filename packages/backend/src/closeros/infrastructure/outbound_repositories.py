"""PostgreSQL repositories for outbound messages and delivery attempts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.outbound_persistence import (
    OutboundDeliveryAttemptRecord,
    OutboundMessageNotFoundError,
    OutboundMessageRecord,
    OutboundMessageVersionConflictError,
    OutboundPersistenceError,
)
from closeros.domain.outbound_message import OutboundMessageStatus
from closeros.infrastructure import outbound_mappers as mappers
from closeros.infrastructure.outbound_orm import OutboundDeliveryAttemptRow, OutboundMessageRow
from closeros.infrastructure.persistence_errors import translate_integrity_error
from closeros.infrastructure.repository_helpers import tenant_scoped_get


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise translate_integrity_error(
            error,
            constraint_errors={},
            default=OutboundPersistenceError,
            message="outbound message persistence integrity error",
        ) from error


class SqlAlchemyOutboundMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, record: OutboundMessageRecord) -> None:
        self._session.add(mappers.outbound_record_to_row(record))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
    ) -> OutboundMessageRecord | None:
        row = await tenant_scoped_get(
            self._session,
            OutboundMessageRow,
            tenant_id=tenant_id,
            record_id=message_id,
        )
        return None if row is None else mappers.outbound_row_to_record(row)

    async def get_by_id_for_update(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
    ) -> OutboundMessageRecord | None:
        statement = (
            select(OutboundMessageRow)
            .where(
                OutboundMessageRow.tenant_id == tenant_id,
                OutboundMessageRow.id == message_id,
            )
            .with_for_update()
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.outbound_row_to_record(row)

    async def get_by_provider_message_id(
        self,
        *,
        tenant_id: UUID,
        channel_connection_id: UUID,
        provider_message_id: str,
    ) -> OutboundMessageRecord | None:
        statement = select(OutboundMessageRow).where(
            OutboundMessageRow.tenant_id == tenant_id,
            OutboundMessageRow.channel_connection_id == channel_connection_id,
            OutboundMessageRow.provider_message_id == provider_message_id,
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.outbound_row_to_record(row)

    async def update(
        self,
        *,
        record: OutboundMessageRecord,
        expected_version: int,
    ) -> OutboundMessageRecord:
        row = (
            await self._session.execute(
                select(OutboundMessageRow)
                .where(
                    OutboundMessageRow.tenant_id == record.tenant_id,
                    OutboundMessageRow.id == record.id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise OutboundMessageNotFoundError("outbound message not found")
        if row.version != expected_version:
            raise OutboundMessageVersionConflictError("outbound message version conflict")
        row.kind = record.kind.value
        row.status = record.status.value
        row.encrypted_content_id = record.encrypted_content_id
        row.provider_template_id = record.provider_template_id
        row.approved_by_user_id = record.approved_by_user_id
        row.provider_message_id = record.provider_message_id
        row.failure_code = record.failure_code
        row.approved_at = record.approved_at
        row.queued_at = record.queued_at
        row.sent_at = record.sent_at
        row.completed_at = record.completed_at
        row.updated_at = record.updated_at
        row.version = record.version
        await _flush(self._session)
        return mappers.outbound_row_to_record(row)

    async def list_delivery_unknown(
        self,
        *,
        tenant_id: UUID,
        limit: int,
    ) -> tuple[OutboundMessageRecord, ...]:
        statement = (
            select(OutboundMessageRow)
            .where(
                OutboundMessageRow.tenant_id == tenant_id,
                OutboundMessageRow.status == OutboundMessageStatus.DELIVERY_UNKNOWN.value,
            )
            .order_by(OutboundMessageRow.updated_at.asc())
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.outbound_row_to_record(row) for row in rows)

    async def list_stale_sending(
        self,
        *,
        tenant_id: UUID,
        stale_before: datetime,
        limit: int,
    ) -> tuple[OutboundMessageRecord, ...]:
        statement = (
            select(OutboundMessageRow)
            .where(
                OutboundMessageRow.tenant_id == tenant_id,
                OutboundMessageRow.status == OutboundMessageStatus.SENDING.value,
                OutboundMessageRow.updated_at < stale_before,
            )
            .order_by(OutboundMessageRow.updated_at.asc())
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.outbound_row_to_record(row) for row in rows)


class SqlAlchemyOutboundDeliveryAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, record: OutboundDeliveryAttemptRecord) -> None:
        self._session.add(mappers.delivery_attempt_record_to_row(record))
        await _flush(self._session)

    async def list_for_message(
        self,
        *,
        tenant_id: UUID,
        outbound_message_id: UUID,
    ) -> tuple[OutboundDeliveryAttemptRecord, ...]:
        statement = (
            select(OutboundDeliveryAttemptRow)
            .where(
                OutboundDeliveryAttemptRow.tenant_id == tenant_id,
                OutboundDeliveryAttemptRow.outbound_message_id == outbound_message_id,
            )
            .order_by(OutboundDeliveryAttemptRow.attempt_number.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.delivery_attempt_row_to_record(row) for row in rows)
