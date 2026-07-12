"""PostgreSQL repository for provider media references."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.provider_media_persistence import (
    DuplicateProviderMediaReferenceError,
    ProviderMediaPersistenceError,
    ProviderMediaReferenceRecord,
)
from closeros.infrastructure import outbound_mappers as mappers
from closeros.infrastructure.outbound_orm import ProviderMediaReferenceRow
from closeros.infrastructure.persistence_errors import translate_integrity_error


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise translate_integrity_error(
            error,
            constraint_errors={
                "uq_provider_media_references_tenant_connection_provider_media_id": (
                    DuplicateProviderMediaReferenceError
                ),
            },
            default=ProviderMediaPersistenceError,
            message="provider media persistence integrity error",
        ) from error


class SqlAlchemyProviderMediaReferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, record: ProviderMediaReferenceRecord) -> None:
        self._session.add(mappers.media_record_to_row(record))
        await _flush(self._session)

    async def get_by_provider_media_id(
        self,
        *,
        tenant_id: UUID,
        channel_connection_id: UUID,
        provider_media_id: str,
    ) -> ProviderMediaReferenceRecord | None:
        statement = select(ProviderMediaReferenceRow).where(
            ProviderMediaReferenceRow.tenant_id == tenant_id,
            ProviderMediaReferenceRow.channel_connection_id == channel_connection_id,
            ProviderMediaReferenceRow.provider_media_id == provider_media_id,
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.media_row_to_record(row)

    async def list_for_thread(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID,
    ) -> tuple[ProviderMediaReferenceRecord, ...]:
        statement = (
            select(ProviderMediaReferenceRow)
            .where(
                ProviderMediaReferenceRow.tenant_id == tenant_id,
                ProviderMediaReferenceRow.conversation_thread_id == conversation_thread_id,
            )
            .order_by(ProviderMediaReferenceRow.created_at.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.media_row_to_record(row) for row in rows)
