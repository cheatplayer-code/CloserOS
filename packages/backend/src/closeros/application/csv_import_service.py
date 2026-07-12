"""Application service for controlled encrypted CSV import lifecycle."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.content_encryption_service import (
    ContentEncryptionService,
    ContentEncryptionUnavailableError,
)
from closeros.application.csv_import_persistence import (
    CsvImportRecordNotFoundError,
    CsvImportRowErrorQuery,
    CsvImportStaleVersionError,
    DuplicateCsvImportBatchError,
)
from closeros.application.ingestion_audit import (
    csv_import_cancelled_event,
    csv_import_started_event,
    csv_import_uploaded_event,
)
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.outbox_persistence import DuplicateOutboxJobError
from closeros.application.provider_ports import ImportContentScanner
from closeros.domain.audit import AuditActorType
from closeros.domain.canonical_enums import ChannelConnectionStatus
from closeros.domain.csv_import import (
    CsvColumnMapping,
    CsvDelimiter,
    CsvImportBatch,
    CsvImportRowError,
    CsvImportStatus,
    CsvSourceEncoding,
)
from closeros.domain.encrypted_content import ContentEncoding, EncryptedContentKind
from closeros.domain.outbox import OutboxJobKind, OutboxJobReference, build_outbox_job

CSV_MAX_BODY_BYTES = 10 * 1024 * 1024
CSV_MIN_COLUMNS = 1
CSV_MAX_COLUMNS = 50
CSV_MAX_DATA_ROWS = 50_000
CSV_MAX_FIELD_BYTES = 16 * 1024
CSV_IMPORT_EXPIRY_DAYS = 30

_ACTIVE_CONNECTION_STATUSES = frozenset(
    {
        ChannelConnectionStatus.ACTIVE,
        ChannelConnectionStatus.DEGRADED,
    }
)

_DELIMITER_MAP = {
    CsvDelimiter.COMMA: ",",
    CsvDelimiter.SEMICOLON: ";",
    CsvDelimiter.TAB: "\t",
}


class CsvImportServiceError(Exception):
    """Base class for safe CSV import service failures."""


class CsvImportValidationError(CsvImportServiceError):
    """Raised when CSV import input fails validation."""


class CsvImportUnavailableError(CsvImportServiceError):
    """Raised when CSV import persistence cannot complete."""


@dataclass(frozen=True, slots=True)
class CsvImportPreviewColumn:
    index: int
    label: str


@dataclass(frozen=True, slots=True)
class CsvImportPreviewResult:
    import_id: UUID
    columns: tuple[CsvImportPreviewColumn, ...]
    total_rows: int


@dataclass(frozen=True, slots=True)
class CsvImportStartResult:
    import_id: UUID
    outbox_job_id: UUID


@dataclass(frozen=True, slots=True)
class CsvImportStatusView:
    import_id: UUID
    status: CsvImportStatus
    total_rows: int
    succeeded_count: int
    failed_count: int
    next_row_number: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    row_errors: tuple[CsvImportRowError, ...]


_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]


def _csv_import_deduplication_key(*, import_id: UUID) -> str:
    return f"csv_import_{import_id}"


@dataclass(frozen=True, slots=True)
class CsvImportService:
    uow_factory: _UnitOfWorkFactory
    content_encryption: ContentEncryptionService
    content_scanner: ImportContentScanner
    uuid_factory: _UuidFactory

    async def preview_upload(
        self,
        *,
        tenant_id: UUID,
        channel_connection_id: UUID,
        creator_user_id: UUID,
        csv_bytes: bytes,
        delimiter: CsvDelimiter,
        source_encoding: CsvSourceEncoding,
        lawful_source_confirmed_at: datetime,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
        idempotency_key: str | None = None,
    ) -> CsvImportPreviewResult:
        _validate_csv_bytes(csv_bytes)
        parsed = _parse_csv(
            csv_bytes=csv_bytes, delimiter=delimiter, source_encoding=source_encoding
        )
        scanned = await self.content_scanner.scan_csv_bytes(content=csv_bytes)
        if not scanned:
            raise CsvImportValidationError("csv content rejected")

        created_at = lawful_source_confirmed_at
        expires_at = created_at + timedelta(days=CSV_IMPORT_EXPIRY_DAYS)
        import_id = self.uuid_factory()
        content_id = self.uuid_factory()

        uow = self.uow_factory()
        async with uow:
            if idempotency_key is not None:
                existing = await uow.csv_import_batches.get_by_idempotency_key(
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                )
                if existing is not None:
                    return CsvImportPreviewResult(
                        import_id=existing.id,
                        columns=_preview_columns(parsed.headers),
                        total_rows=existing.total_rows,
                    )

            connection = await uow.channel_connections.get_by_id(
                tenant_id=tenant_id,
                connection_id=channel_connection_id,
            )
            if connection is None or connection.status not in _ACTIVE_CONNECTION_STATUSES:
                raise CsvImportValidationError("channel connection unavailable")

            try:
                await self.content_encryption.encrypt_and_persist(
                    uow,
                    content_id=content_id,
                    tenant_id=tenant_id,
                    kind=EncryptedContentKind.CSV_IMPORT,
                    encoding=ContentEncoding.UTF8,
                    plaintext=csv_bytes,
                    created_at=created_at,
                )
                batch = CsvImportBatch(
                    id=import_id,
                    tenant_id=tenant_id,
                    channel_connection_id=channel_connection_id,
                    source_content_id=content_id,
                    creator_user_id=creator_user_id,
                    status=CsvImportStatus.UPLOADED,
                    delimiter=delimiter,
                    source_encoding=source_encoding,
                    lawful_source_confirmed_at=lawful_source_confirmed_at,
                    mapping=None,
                    total_rows=parsed.total_rows,
                    next_row_number=1,
                    succeeded_count=0,
                    failed_count=0,
                    created_at=created_at,
                    started_at=None,
                    completed_at=None,
                    expires_at=expires_at,
                    version=1,
                    idempotency_key=idempotency_key,
                )
                await uow.csv_import_batches.add(batch)
                await append_required_audit_event(
                    uow.audit_events,
                    csv_import_uploaded_event(
                        tenant_id=tenant_id,
                        import_id=import_id,
                        occurred_at=created_at,
                        audit_context=audit_context,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        event_id=self.uuid_factory(),
                    ),
                )
                await uow.commit()
            except (
                ContentEncryptionUnavailableError,
                DuplicateCsvImportBatchError,
            ) as error:
                await uow.rollback()
                raise CsvImportUnavailableError("csv import preview failed") from error

        return CsvImportPreviewResult(
            import_id=import_id,
            columns=_preview_columns(parsed.headers),
            total_rows=parsed.total_rows,
        )

    async def start_import(
        self,
        *,
        tenant_id: UUID,
        import_id: UUID,
        mapping: CsvColumnMapping,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
        occurred_at: datetime,
    ) -> CsvImportStartResult:
        outbox_job_id = self.uuid_factory()
        uow = self.uow_factory()
        async with uow:
            batch = await uow.csv_import_batches.get_for_update(
                tenant_id=tenant_id,
                import_id=import_id,
            )
            if batch is None:
                raise CsvImportRecordNotFoundError("csv import batch not found")
            if batch.status not in {CsvImportStatus.UPLOADED, CsvImportStatus.READY}:
                raise CsvImportValidationError("csv import cannot be started")

            updated = replace(
                batch,
                status=CsvImportStatus.READY,
                mapping=mapping,
            )
            try:
                await uow.csv_import_batches.update(updated)
                await uow.outbox_jobs.enqueue(
                    build_outbox_job(
                        job_id=outbox_job_id,
                        tenant_id=tenant_id,
                        job_kind=OutboxJobKind.CSV_IMPORT,
                        reference=OutboxJobReference(
                            resource_type="csv_import_batch",
                            resource_id=import_id,
                            schema_version=1,
                            tenant_id=tenant_id,
                        ),
                        deduplication_key=_csv_import_deduplication_key(import_id=import_id),
                        created_at=occurred_at,
                    )
                )
                await append_required_audit_event(
                    uow.audit_events,
                    csv_import_started_event(
                        tenant_id=tenant_id,
                        import_id=import_id,
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        event_id=self.uuid_factory(),
                    ),
                )
                await uow.commit()
            except (DuplicateOutboxJobError, CsvImportStaleVersionError) as error:
                await uow.rollback()
                raise CsvImportUnavailableError("csv import start failed") from error

        return CsvImportStartResult(import_id=import_id, outbox_job_id=outbox_job_id)

    async def cancel_import(
        self,
        *,
        tenant_id: UUID,
        import_id: UUID,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
        occurred_at: datetime,
    ) -> None:
        uow = self.uow_factory()
        async with uow:
            batch = await uow.csv_import_batches.get_for_update(
                tenant_id=tenant_id,
                import_id=import_id,
            )
            if batch is None:
                raise CsvImportRecordNotFoundError("csv import batch not found")
            if batch.status in {
                CsvImportStatus.COMPLETED,
                CsvImportStatus.COMPLETED_WITH_ERRORS,
                CsvImportStatus.CANCELLED,
            }:
                raise CsvImportValidationError("csv import cannot be cancelled")

            updated = replace(batch, status=CsvImportStatus.CANCELLED, completed_at=occurred_at)
            try:
                await uow.csv_import_batches.update(updated)
                await append_required_audit_event(
                    uow.audit_events,
                    csv_import_cancelled_event(
                        tenant_id=tenant_id,
                        import_id=import_id,
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        event_id=self.uuid_factory(),
                    ),
                )
                await uow.commit()
            except CsvImportStaleVersionError as error:
                await uow.rollback()
                raise CsvImportUnavailableError("csv import cancel failed") from error

    async def get_status(
        self,
        *,
        tenant_id: UUID,
        import_id: UUID,
        row_error_query: CsvImportRowErrorQuery | None = None,
    ) -> CsvImportStatusView:
        query = row_error_query or CsvImportRowErrorQuery()
        uow = self.uow_factory()
        async with uow:
            batch = await uow.csv_import_batches.get_by_id(
                tenant_id=tenant_id,
                import_id=import_id,
            )
            if batch is None:
                raise CsvImportRecordNotFoundError("csv import batch not found")
            row_errors = await uow.csv_import_row_errors.list_by_import(
                tenant_id=tenant_id,
                import_id=import_id,
                query=query,
            )

        return CsvImportStatusView(
            import_id=batch.id,
            status=batch.status,
            total_rows=batch.total_rows,
            succeeded_count=batch.succeeded_count,
            failed_count=batch.failed_count,
            next_row_number=batch.next_row_number,
            created_at=batch.created_at,
            started_at=batch.started_at,
            completed_at=batch.completed_at,
            row_errors=row_errors,
        )


@dataclass(frozen=True, slots=True)
class _ParsedCsv:
    headers: tuple[str, ...]
    total_rows: int


def _preview_columns(headers: tuple[str, ...]) -> tuple[CsvImportPreviewColumn, ...]:
    return tuple(
        CsvImportPreviewColumn(index=index, label=label) for index, label in enumerate(headers)
    )


def _validate_csv_bytes(csv_bytes: bytes) -> None:
    if type(csv_bytes) is not bytes or not csv_bytes:
        raise CsvImportValidationError("csv body must not be empty")
    if len(csv_bytes) > CSV_MAX_BODY_BYTES:
        raise CsvImportValidationError("csv body exceeds allowed size")
    if b"\x00" in csv_bytes:
        raise CsvImportValidationError("csv body contains invalid bytes")


def _decode_csv_bytes(csv_bytes: bytes, *, source_encoding: CsvSourceEncoding) -> str:
    if source_encoding is CsvSourceEncoding.UTF8_BOM:
        return csv_bytes.decode("utf-8-sig")
    try:
        return csv_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CsvImportValidationError("csv encoding is invalid") from error


def _parse_csv(
    *,
    csv_bytes: bytes,
    delimiter: CsvDelimiter,
    source_encoding: CsvSourceEncoding,
) -> _ParsedCsv:
    text = _decode_csv_bytes(csv_bytes, source_encoding=source_encoding)
    reader = csv.reader(io.StringIO(text), delimiter=_DELIMITER_MAP[delimiter])
    try:
        headers = next(reader)
    except StopIteration as error:
        raise CsvImportValidationError("csv headers are missing") from error

    if not headers:
        raise CsvImportValidationError("csv headers are missing")
    if not CSV_MIN_COLUMNS <= len(headers) <= CSV_MAX_COLUMNS:
        raise CsvImportValidationError("csv column count is invalid")

    normalized_headers = [header.strip() for header in headers]
    if any(not header for header in normalized_headers):
        raise CsvImportValidationError("csv headers must not be empty")
    if len(set(normalized_headers)) != len(normalized_headers):
        raise CsvImportValidationError("csv headers must be unique")

    total_rows = 0
    for row in reader:
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) > CSV_MAX_COLUMNS:
            raise CsvImportValidationError("csv row exceeds allowed column count")
        for cell in row:
            if len(cell.encode("utf-8")) > CSV_MAX_FIELD_BYTES:
                raise CsvImportValidationError("csv field exceeds allowed size")
        total_rows += 1
        if total_rows > CSV_MAX_DATA_ROWS:
            raise CsvImportValidationError("csv row count exceeds allowed limit")

    return _ParsedCsv(headers=tuple(normalized_headers), total_rows=total_rows)
