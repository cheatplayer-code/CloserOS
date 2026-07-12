"""PostgreSQL repository for provider message templates."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.provider_template_persistence import (
    ProviderMessageTemplateRecord,
    ProviderTemplatePersistenceError,
)
from closeros.infrastructure import outbound_mappers as mappers
from closeros.infrastructure.persistence_errors import translate_integrity_error
from closeros.infrastructure.repository_helpers import tenant_scoped_get
from closeros.infrastructure.whatsapp_orm import ProviderMessageTemplateRow


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise translate_integrity_error(
            error,
            constraint_errors={},
            default=ProviderTemplatePersistenceError,
            message="provider template persistence integrity error",
        ) from error


class SqlAlchemyProviderMessageTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        record: ProviderMessageTemplateRecord,
    ) -> ProviderMessageTemplateRecord:
        statement = select(ProviderMessageTemplateRow).where(
            ProviderMessageTemplateRow.tenant_id == record.tenant_id,
            ProviderMessageTemplateRow.whatsapp_connection_id == record.whatsapp_connection_id,
            ProviderMessageTemplateRow.provider_template_id == record.provider_template_id,
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        if row is None:
            self._session.add(mappers.template_record_to_row(record))
            await _flush(self._session)
            return record
        row.name = record.name
        row.language_code = record.language_code
        row.category = record.category
        row.approval_status = record.approval_status.value
        row.component_shape = list(record.component_shape)
        row.parameter_count = record.parameter_count
        row.last_synced_at = record.last_synced_at
        row.updated_at = record.updated_at
        row.version = record.version
        await _flush(self._session)
        return mappers.template_row_to_record(row)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        template_id: UUID,
    ) -> ProviderMessageTemplateRecord | None:
        row = await tenant_scoped_get(
            self._session,
            ProviderMessageTemplateRow,
            tenant_id=tenant_id,
            record_id=template_id,
        )
        return None if row is None else mappers.template_row_to_record(row)

    async def list_by_connection(
        self,
        *,
        tenant_id: UUID,
        whatsapp_connection_id: UUID,
    ) -> tuple[ProviderMessageTemplateRecord, ...]:
        statement = (
            select(ProviderMessageTemplateRow)
            .where(
                ProviderMessageTemplateRow.tenant_id == tenant_id,
                ProviderMessageTemplateRow.whatsapp_connection_id == whatsapp_connection_id,
            )
            .order_by(ProviderMessageTemplateRow.name.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.template_row_to_record(row) for row in rows)
