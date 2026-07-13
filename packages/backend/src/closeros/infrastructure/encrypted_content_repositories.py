"""PostgreSQL repository implementations for encrypted content persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.encrypted_content_persistence import (
    DuplicateEncryptedContentError,
    EncryptedContentPersistenceError,
    EncryptedContentRecordNotFoundError,
    EncryptedContentReferenceError,
    EncryptedContentRetentionFilter,
)
from closeros.domain.encrypted_content import EncryptedContent, EncryptedContentKind, WrappedDataKey
from closeros.infrastructure import encrypted_content_mappers as mappers
from closeros.infrastructure.encrypted_content_orm import EncryptedContentRow
from closeros.infrastructure.persistence_errors import translate_integrity_error
from closeros.infrastructure.repository_helpers import tenant_scoped_get

_CONSTRAINT_ERRORS: dict[str, type[EncryptedContentPersistenceError]] = {
    "pk_encrypted_contents": DuplicateEncryptedContentError,
    "uq_encrypted_contents_tenant_id_id": DuplicateEncryptedContentError,
    "fk_messages_tenant_id_content_id_encrypted_contents": EncryptedContentReferenceError,
    "fk_message_edit_events_tenant_id_content_id_encrypted_contents": (
        EncryptedContentReferenceError
    ),
    "fk_webhook_events_tenant_id_encrypted_payload_content_id_encrypted_contents": (
        EncryptedContentReferenceError
    ),
}


def _translate_integrity_error(error: IntegrityError) -> EncryptedContentPersistenceError:
    return translate_integrity_error(
        error,
        constraint_errors=_CONSTRAINT_ERRORS,
        default=EncryptedContentPersistenceError,
        message="encrypted content persistence integrity error",
    )


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise _translate_integrity_error(error) from error


class SqlAlchemyEncryptedContentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, content: EncryptedContent) -> None:
        self._session.add(mappers.encrypted_content_to_row(content))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
    ) -> EncryptedContent | None:
        row = await tenant_scoped_get(
            self._session,
            EncryptedContentRow,
            tenant_id=tenant_id,
            record_id=content_id,
        )
        return None if row is None else mappers.encrypted_content_to_domain(row)

    async def get_for_update(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
    ) -> EncryptedContent | None:
        statement = (
            select(EncryptedContentRow)
            .where(
                EncryptedContentRow.id == content_id,
                EncryptedContentRow.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.encrypted_content_to_domain(row)

    async def replace_wrapped_key(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        wrapped_data_key: WrappedDataKey,
    ) -> None:
        statement = (
            select(EncryptedContentRow)
            .where(
                EncryptedContentRow.id == content_id,
                EncryptedContentRow.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        if row is None:
            raise EncryptedContentRecordNotFoundError("encrypted content not found")
        mappers.apply_wrapped_data_key(row, wrapped_data_key)
        await _flush(self._session)

    async def list_by_tenant_and_kind(
        self,
        *,
        tenant_id: UUID,
        kind: EncryptedContentKind,
        limit: int = 100,
    ) -> tuple[EncryptedContent, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        statement = (
            select(EncryptedContentRow)
            .where(
                EncryptedContentRow.tenant_id == tenant_id,
                EncryptedContentRow.kind == kind.value,
            )
            .order_by(
                EncryptedContentRow.created_at.desc(),
                EncryptedContentRow.id.desc(),
            )
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.encrypted_content_to_domain(row) for row in rows)

    async def count_due_for_retention(
        self,
        *,
        query_filter: EncryptedContentRetentionFilter,
    ) -> int:
        from sqlalchemy import func, select

        statement = select(func.count()).select_from(EncryptedContentRow)
        if query_filter.tenant_id is not None:
            statement = statement.where(
                EncryptedContentRow.tenant_id == query_filter.tenant_id,
            )
        if query_filter.expires_before is not None:
            statement = statement.where(
                EncryptedContentRow.expires_at <= query_filter.expires_before,
            )
        result = await self._session.execute(statement)
        counted = result.scalar_one()
        return int(counted)

    async def list_due_for_retention(
        self,
        *,
        query_filter: EncryptedContentRetentionFilter,
    ) -> tuple[EncryptedContent, ...]:
        if query_filter.limit < 1:
            raise ValueError("limit must be positive")

        statement = select(EncryptedContentRow)
        if query_filter.tenant_id is not None:
            statement = statement.where(
                EncryptedContentRow.tenant_id == query_filter.tenant_id,
            )
        if query_filter.expires_before is not None:
            statement = statement.where(
                EncryptedContentRow.expires_at <= query_filter.expires_before,
            )
        statement = statement.order_by(
            EncryptedContentRow.expires_at.asc(),
            EncryptedContentRow.id.asc(),
        ).limit(query_filter.limit)
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.encrypted_content_to_domain(row) for row in rows)

    async def delete(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
    ) -> None:
        from sqlalchemy import delete

        statement = delete(EncryptedContentRow).where(
            EncryptedContentRow.tenant_id == tenant_id,
            EncryptedContentRow.id == content_id,
        )
        await self._session.execute(statement)
        await _flush(self._session)
