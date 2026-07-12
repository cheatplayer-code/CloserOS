"""PostgreSQL repository implementations for controlled CSV import persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.csv_import_persistence import (
    CsvImportPersistenceError,
    CsvImportRecordNotFoundError,
    CsvImportRowErrorQuery,
    CsvImportStaleVersionError,
    DuplicateCsvImportBatchError,
)
from closeros.domain.csv_import import CsvImportBatch, CsvImportRowError
from closeros.infrastructure import csv_import_mappers as mappers
from closeros.infrastructure.csv_import_orm import CsvImportBatchRow, CsvImportRowErrorRow
from closeros.infrastructure.persistence_errors import translate_integrity_error
from closeros.infrastructure.repository_helpers import tenant_scoped_get, tenant_scoped_get_required

_CONSTRAINT_ERRORS: dict[str, type[CsvImportPersistenceError]] = {
    "uq_csv_import_batches_tenant_id_idempotency_key": DuplicateCsvImportBatchError,
}


def _translate_integrity_error(error: IntegrityError) -> CsvImportPersistenceError:
    return translate_integrity_error(
        error,
        constraint_errors=_CONSTRAINT_ERRORS,
        default=CsvImportPersistenceError,
        message="csv import persistence integrity error",
    )


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise _translate_integrity_error(error) from error


class SqlAlchemyCsvImportBatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, batch: CsvImportBatch) -> None:
        self._session.add(mappers.csv_import_batch_to_row(batch))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        import_id: UUID,
    ) -> CsvImportBatch | None:
        row = await tenant_scoped_get(
            self._session,
            CsvImportBatchRow,
            tenant_id=tenant_id,
            record_id=import_id,
        )
        return None if row is None else mappers.csv_import_batch_to_domain(row)

    async def get_for_update(
        self,
        *,
        tenant_id: UUID,
        import_id: UUID,
    ) -> CsvImportBatch | None:
        statement = (
            select(CsvImportBatchRow)
            .where(
                CsvImportBatchRow.id == import_id,
                CsvImportBatchRow.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.csv_import_batch_to_domain(row)

    async def get_by_idempotency_key(
        self,
        *,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> CsvImportBatch | None:
        row = (
            await self._session.execute(
                select(CsvImportBatchRow).where(
                    CsvImportBatchRow.tenant_id == tenant_id,
                    CsvImportBatchRow.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.csv_import_batch_to_domain(row)

    async def update(self, batch: CsvImportBatch) -> None:
        row = await tenant_scoped_get_required(
            self._session,
            CsvImportBatchRow,
            tenant_id=batch.tenant_id,
            record_id=batch.id,
            not_found_error=CsvImportRecordNotFoundError,
            not_found_message="csv import batch not found",
        )
        if row.version != batch.version:
            raise CsvImportStaleVersionError("csv import batch version mismatch")
        mappers.update_csv_import_batch_row(row, batch)
        row.version = batch.version + 1
        await _flush(self._session)


class SqlAlchemyCsvImportRowErrorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, error: CsvImportRowError) -> None:
        batch_row = await self._session.get(CsvImportBatchRow, error.import_id)
        if batch_row is None:
            raise CsvImportRecordNotFoundError("csv import batch not found")
        self._session.add(mappers.csv_import_row_error_to_row(error, tenant_id=batch_row.tenant_id))
        await _flush(self._session)

    async def list_by_import(
        self,
        *,
        tenant_id: UUID,
        import_id: UUID,
        query: CsvImportRowErrorQuery,
    ) -> tuple[CsvImportRowError, ...]:
        if query.limit < 1:
            raise ValueError("limit must be positive")
        if query.offset < 0:
            raise ValueError("offset must not be negative")

        statement = (
            select(CsvImportRowErrorRow)
            .where(
                CsvImportRowErrorRow.tenant_id == tenant_id,
                CsvImportRowErrorRow.import_id == import_id,
            )
            .order_by(CsvImportRowErrorRow.row_number.asc())
            .offset(query.offset)
            .limit(query.limit)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.csv_import_row_error_to_domain(row) for row in rows)
