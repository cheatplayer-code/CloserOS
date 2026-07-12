"""PostgreSQL repository for content sanitization records."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.content_sanitization_persistence import (
    ContentSanitizationPersistenceError,
    DuplicateContentSanitizationError,
)
from closeros.domain.content_sanitization import ContentSanitization
from closeros.domain.privacy_redaction import SanitizationStatus
from closeros.infrastructure import content_sanitization_mappers as mappers
from closeros.infrastructure.content_sanitization_orm import (
    ContentSanitizationCategoryCountRow,
    ContentSanitizationRow,
)
from closeros.infrastructure.persistence_errors import translate_integrity_error

_CONSTRAINT_ERRORS: dict[str, type[ContentSanitizationPersistenceError]] = {
    "uq_content_sanitizations_tenant_source_policy": DuplicateContentSanitizationError,
}


def _translate_integrity_error(error: IntegrityError) -> ContentSanitizationPersistenceError:
    return translate_integrity_error(
        error,
        constraint_errors=_CONSTRAINT_ERRORS,
        default=ContentSanitizationPersistenceError,
        message="content sanitization persistence integrity error",
    )


class SqlAlchemyContentSanitizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_completed_by_source(
        self,
        *,
        tenant_id: UUID,
        source_content_id: UUID,
        policy_version: str,
    ) -> ContentSanitization | None:
        statement = select(ContentSanitizationRow).where(
            ContentSanitizationRow.tenant_id == tenant_id,
            ContentSanitizationRow.source_content_id == source_content_id,
            ContentSanitizationRow.policy_version == policy_version,
            ContentSanitizationRow.status == SanitizationStatus.COMPLETED.value,
        )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        category_rows = await self._load_category_rows(
            tenant_id=tenant_id,
            sanitization_id=row.id,
        )
        return mappers.to_domain(row, category_rows=category_rows)

    async def append_completed(self, *, record: ContentSanitization) -> None:
        if record.status is not SanitizationStatus.COMPLETED:
            raise ContentSanitizationPersistenceError("only completed records may be appended")
        row = mappers.to_row(record)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error
        for entry in record.category_counts:
            self._session.add(
                mappers.category_count_to_row(
                    tenant_id=record.tenant_id,
                    sanitization_id=record.id,
                    entry=entry,
                )
            )
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error

    async def _load_category_rows(
        self,
        *,
        tenant_id: UUID,
        sanitization_id: UUID,
    ) -> tuple[ContentSanitizationCategoryCountRow, ...]:
        statement = (
            select(ContentSanitizationCategoryCountRow)
            .where(
                ContentSanitizationCategoryCountRow.tenant_id == tenant_id,
                ContentSanitizationCategoryCountRow.sanitization_id == sanitization_id,
            )
            .order_by(ContentSanitizationCategoryCountRow.category.asc())
        )
        result = await self._session.execute(statement)
        return tuple(result.scalars().all())
