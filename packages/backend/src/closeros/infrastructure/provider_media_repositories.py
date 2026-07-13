"""PostgreSQL repository for provider media references."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.provider_media_persistence import (
    DuplicateProviderMediaReferenceError,
    ProviderMediaPersistenceError,
    ProviderMediaReferenceRecord,
)
from closeros.domain.provider_media_reference import MediaQuarantineStatus
from closeros.infrastructure import outbound_mappers as mappers
from closeros.infrastructure.outbound_orm import ProviderMediaReferenceRow
from closeros.infrastructure.persistence_errors import translate_integrity_error
from closeros.infrastructure.xy_repositories import update_provider_media_status


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

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        media_reference_id: UUID,
    ) -> ProviderMediaReferenceRecord | None:
        statement = select(ProviderMediaReferenceRow).where(
            ProviderMediaReferenceRow.tenant_id == tenant_id,
            ProviderMediaReferenceRow.id == media_reference_id,
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.media_row_to_record(row)

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

    async def update_status(
        self,
        *,
        tenant_id: UUID,
        media_reference_id: UUID,
        quarantine_status: MediaQuarantineStatus,
        updated_at: datetime,
        mime_type: str | None = None,
        size_bytes: int | None = None,
        encrypted_content_id: UUID | None = None,
        clear_encrypted_content_id: bool = False,
    ) -> None:
        await update_provider_media_status(
            self._session,
            tenant_id=tenant_id,
            media_reference_id=media_reference_id,
            quarantine_status=quarantine_status,
            updated_at=updated_at,
            mime_type=mime_type,
            size_bytes=size_bytes,
            encrypted_content_id=encrypted_content_id,
            clear_encrypted_content_id=clear_encrypted_content_id,
        )
