"""Mappers between CSV import domain entities and SQLAlchemy rows."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from closeros.domain.csv_import import (
    CsvColumnMapping,
    CsvDelimiter,
    CsvImportBatch,
    CsvImportErrorCode,
    CsvImportRowError,
    CsvImportStatus,
    CsvSourceEncoding,
)
from closeros.infrastructure.csv_import_orm import CsvImportBatchRow, CsvImportRowErrorRow


def _mapping_to_json(mapping: CsvColumnMapping | None) -> dict[str, int] | None:
    if mapping is None:
        return None
    return mapping.as_dict()


def _mapping_from_json(value: dict[str, object] | None) -> CsvColumnMapping | None:
    if value is None:
        return None
    normalized: dict[str, int] = {}
    for key, column_index in value.items():
        if not isinstance(column_index, int):
            raise TypeError("mapping column index must be an integer")
        normalized[str(key)] = column_index
    return CsvColumnMapping.from_dict(normalized)


def csv_import_batch_to_row(batch: CsvImportBatch) -> CsvImportBatchRow:
    return CsvImportBatchRow(
        id=batch.id,
        tenant_id=batch.tenant_id,
        channel_connection_id=batch.channel_connection_id,
        source_content_id=batch.source_content_id,
        creator_user_id=batch.creator_user_id,
        status=batch.status.value,
        delimiter=batch.delimiter.value,
        source_encoding=batch.source_encoding.value,
        lawful_source_confirmed_at=batch.lawful_source_confirmed_at,
        mapping=_mapping_to_json(batch.mapping),
        total_rows=batch.total_rows,
        next_row_number=batch.next_row_number,
        succeeded_count=batch.succeeded_count,
        failed_count=batch.failed_count,
        created_at=batch.created_at,
        started_at=batch.started_at,
        completed_at=batch.completed_at,
        expires_at=batch.expires_at,
        version=batch.version,
        idempotency_key=batch.idempotency_key,
    )


def csv_import_batch_to_domain(row: CsvImportBatchRow) -> CsvImportBatch:
    return CsvImportBatch(
        id=row.id,
        tenant_id=row.tenant_id,
        channel_connection_id=row.channel_connection_id,
        source_content_id=row.source_content_id,
        creator_user_id=row.creator_user_id,
        status=CsvImportStatus(row.status),
        delimiter=CsvDelimiter(row.delimiter),
        source_encoding=CsvSourceEncoding(row.source_encoding),
        lawful_source_confirmed_at=row.lawful_source_confirmed_at,
        mapping=_mapping_from_json(row.mapping),
        total_rows=row.total_rows,
        next_row_number=row.next_row_number,
        succeeded_count=row.succeeded_count,
        failed_count=row.failed_count,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        expires_at=row.expires_at,
        version=row.version,
        idempotency_key=row.idempotency_key,
    )


def update_csv_import_batch_row(row: CsvImportBatchRow, batch: CsvImportBatch) -> None:
    row.status = batch.status.value
    row.mapping = cast(dict[str, object] | None, _mapping_to_json(batch.mapping))
    row.total_rows = batch.total_rows
    row.next_row_number = batch.next_row_number
    row.succeeded_count = batch.succeeded_count
    row.failed_count = batch.failed_count
    row.started_at = batch.started_at
    row.completed_at = batch.completed_at


def csv_import_row_error_to_row(
    error: CsvImportRowError, *, tenant_id: UUID
) -> CsvImportRowErrorRow:
    return CsvImportRowErrorRow(
        import_id=error.import_id,
        row_number=error.row_number,
        tenant_id=tenant_id,
        error_code=error.error_code.value,
        occurred_at=error.occurred_at,
    )


def csv_import_row_error_to_domain(row: CsvImportRowErrorRow) -> CsvImportRowError:
    return CsvImportRowError(
        import_id=row.import_id,
        row_number=row.row_number,
        error_code=CsvImportErrorCode(row.error_code),
        occurred_at=row.occurred_at,
    )
