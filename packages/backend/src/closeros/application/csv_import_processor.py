"""Outbox handler that processes controlled encrypted CSV imports in resumable chunks."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.canonical_persistence import DuplicateMessageError
from closeros.application.content_audit import raw_message_stored_event
from closeros.application.content_encryption_service import (
    ContentAccessDeniedError,
    ContentEncryptionService,
    ContentEncryptionUnavailableError,
)
from closeros.application.csv_import_persistence import CsvImportStaleVersionError
from closeros.application.ingestion_audit import csv_import_completed_event
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.outbox_persistence import DuplicateOutboxJobError
from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.audit import AuditActorType
from closeros.domain.canonical_enums import MessageDirection, ParticipantSenderType
from closeros.domain.conversation_thread import ConversationThread
from closeros.domain.csv_import import (
    CsvColumnMapping,
    CsvDelimiter,
    CsvImportBatch,
    CsvImportErrorCode,
    CsvImportRowError,
    CsvImportStatus,
    CsvSourceEncoding,
)
from closeros.domain.encrypted_content import ContentEncoding, EncryptedContentKind
from closeros.domain.message import Message
from closeros.domain.outbox import (
    OutboxErrorCode,
    OutboxJob,
    OutboxJobKind,
    OutboxJobReference,
    build_outbox_job,
)

CSV_IMPORT_CHUNK_SIZE = 250

_DELIMITER_MAP = {
    CsvDelimiter.COMMA: ",",
    CsvDelimiter.SEMICOLON: ";",
    CsvDelimiter.TAB: "\t",
}


class CsvImportHandlerError(Exception):
    """Controlled CSV import failure surfaced to the outbox processor."""

    def __init__(
        self,
        *,
        error_code: OutboxErrorCode,
        permanent: bool,
    ) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("csv import processing failed")


_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]


def _content_redact_deduplication_key(*, resource_id: UUID) -> str:
    return f"content_redact_{resource_id}"


def _csv_import_chunk_deduplication_key(*, import_id: UUID, next_row_number: int) -> str:
    return f"csv_import_{import_id}_from_{next_row_number}"


@dataclass(frozen=True, slots=True)
class CsvImportProcessor:
    """Processes csv.import outbox jobs in bounded, resumable row chunks."""

    uow_factory: _UnitOfWorkFactory
    content_encryption: ContentEncryptionService
    service_actor_id: UUID
    uuid_factory: _UuidFactory

    async def handle(self, *, job: OutboxJob) -> None:
        if job.tenant_id is None:
            raise CsvImportHandlerError(
                error_code=OutboxErrorCode.HANDLER_FAILED,
                permanent=True,
            )

        tenant_id = job.tenant_id
        import_id = job.reference.resource_id
        occurred_at = job.processing_started_at or job.created_at
        audit_context = AuditContext(correlation_id=job.id)

        uow = self.uow_factory()
        async with uow:
            try:
                batch = await uow.csv_import_batches.get_for_update(
                    tenant_id=tenant_id,
                    import_id=import_id,
                )
                if batch is None:
                    raise CsvImportHandlerError(
                        error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                        permanent=False,
                    )

                if batch.status in {
                    CsvImportStatus.COMPLETED,
                    CsvImportStatus.COMPLETED_WITH_ERRORS,
                    CsvImportStatus.CANCELLED,
                    CsvImportStatus.FAILED,
                }:
                    return

                if batch.mapping is None:
                    raise CsvImportHandlerError(
                        error_code=OutboxErrorCode.HANDLER_FAILED,
                        permanent=True,
                    )

                if batch.status is CsvImportStatus.READY:
                    processing_batch = replace(
                        batch,
                        status=CsvImportStatus.PROCESSING,
                        started_at=occurred_at,
                    )
                    await uow.csv_import_batches.update(processing_batch)
                    batch = replace(processing_batch, version=processing_batch.version + 1)

                encrypted = await uow.encrypted_contents.get_by_id(
                    tenant_id=tenant_id,
                    content_id=batch.source_content_id,
                )
                if encrypted is None or encrypted.kind is not EncryptedContentKind.CSV_IMPORT:
                    raise CsvImportHandlerError(
                        error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                        permanent=False,
                    )

                try:
                    decrypted = self.content_encryption.data_key_cryptography.decrypt_content(
                        encrypted=encrypted,
                    )
                except Exception as error:
                    raise CsvImportHandlerError(
                        error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                        permanent=False,
                    ) from error

                rows = _load_data_rows(
                    csv_bytes=decrypted.as_bytes(),
                    delimiter=batch.delimiter,
                    source_encoding=batch.source_encoding,
                )
                mapping = batch.mapping
                assert mapping is not None
                start_index = batch.next_row_number - 1
                end_index = min(start_index + CSV_IMPORT_CHUNK_SIZE, len(rows))

                succeeded_delta = 0
                failed_delta = 0
                for row_number in range(start_index + 1, end_index + 1):
                    row = rows[row_number - 1]
                    row_succeeded, row_failed = await self._process_row(
                        uow=uow,
                        batch=batch,
                        row_number=row_number,
                        row=row,
                        mapping=mapping,
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                    )
                    succeeded_delta += row_succeeded
                    failed_delta += row_failed

                next_row_number = end_index + 1
                completed = next_row_number > len(rows)
                total_succeeded = batch.succeeded_count + succeeded_delta
                total_failed = batch.failed_count + failed_delta
                final_status = (
                    CsvImportStatus.COMPLETED
                    if completed and total_failed == 0
                    else CsvImportStatus.COMPLETED_WITH_ERRORS
                    if completed
                    else CsvImportStatus.PROCESSING
                )
                updated_batch = replace(
                    batch,
                    next_row_number=next_row_number,
                    succeeded_count=total_succeeded,
                    failed_count=total_failed,
                    status=final_status,
                    completed_at=occurred_at if completed else batch.completed_at,
                )
                await uow.csv_import_batches.update(updated_batch)

                if not completed:
                    await uow.outbox_jobs.enqueue(
                        build_outbox_job(
                            job_id=self.uuid_factory(),
                            tenant_id=tenant_id,
                            job_kind=OutboxJobKind.CSV_IMPORT,
                            reference=OutboxJobReference(
                                resource_type="csv_import_batch",
                                resource_id=import_id,
                                schema_version=1,
                                tenant_id=tenant_id,
                            ),
                            deduplication_key=_csv_import_chunk_deduplication_key(
                                import_id=import_id,
                                next_row_number=next_row_number,
                            ),
                            created_at=occurred_at,
                        )
                    )
                else:
                    await append_required_audit_event(
                        uow.audit_events,
                        csv_import_completed_event(
                            tenant_id=tenant_id,
                            import_id=import_id,
                            status=final_status,
                            succeeded_count=updated_batch.succeeded_count,
                            failed_count=updated_batch.failed_count,
                            occurred_at=occurred_at,
                            audit_context=audit_context,
                            actor_type=AuditActorType.SERVICE,
                            actor_id=self.service_actor_id,
                            event_id=self.uuid_factory(),
                        ),
                    )

                await uow.commit()
            except CsvImportHandlerError:
                await uow.rollback()
                raise
            except (
                ContentEncryptionUnavailableError,
                ContentAccessDeniedError,
                DuplicateMessageError,
                DuplicateOutboxJobError,
                CsvImportStaleVersionError,
            ) as error:
                await uow.rollback()
                raise CsvImportHandlerError(
                    error_code=OutboxErrorCode.HANDLER_FAILED,
                    permanent=False,
                ) from error
            except Exception as error:
                await uow.rollback()
                raise CsvImportHandlerError(
                    error_code=OutboxErrorCode.HANDLER_FAILED,
                    permanent=False,
                ) from error

    async def _process_row(
        self,
        *,
        uow: IntegratedUnitOfWork,
        batch: CsvImportBatch,
        row_number: int,
        row: tuple[str, ...],
        mapping: CsvColumnMapping,
        occurred_at: datetime,
        audit_context: AuditContext,
    ) -> tuple[int, int]:
        try:
            values = _extract_row_values(row=row, mapping=mapping)
            external_conversation_id = values["external_conversation_id"]
            external_message_id = values["external_message_id"]
            sender_type = ParticipantSenderType(values["sender_type"])
            direction = MessageDirection(values["direction"])
            sent_at = _parse_timestamp(values["sent_at"], field_name="sent_at")
            received_at = _parse_timestamp(values["received_at"], field_name="received_at")
            message_text = values["message_text"].encode("utf-8")
            reply_external_id = values.get("reply_to_external_message_id")
        except ValueError:
            await self._record_row_error(
                uow=uow,
                batch=batch,
                row_number=row_number,
                error_code=CsvImportErrorCode.INVALID_ROW,
                occurred_at=occurred_at,
            )
            return 0, 1

        thread = await self._get_or_create_thread(
            uow=uow,
            batch=batch,
            external_conversation_id=external_conversation_id,
            occurred_at=occurred_at,
        )
        existing = await uow.messages.get_by_external_message_id(
            tenant_id=batch.tenant_id,
            conversation_thread_id=thread.id,
            external_message_id=external_message_id,
        )
        if existing is not None:
            return 1, 0

        reply_to_message_id: UUID | None = None
        if reply_external_id:
            parent = await uow.messages.get_by_external_message_id(
                tenant_id=batch.tenant_id,
                conversation_thread_id=thread.id,
                external_message_id=reply_external_id,
            )
            if parent is None:
                await self._record_row_error(
                    uow=uow,
                    batch=batch,
                    row_number=row_number,
                    error_code=CsvImportErrorCode.THREAD_UNAVAILABLE,
                    occurred_at=occurred_at,
                )
                return 0, 1
            reply_to_message_id = parent.id

        message_id = self.uuid_factory()
        content_id = self.uuid_factory()
        outbox_job_id = self.uuid_factory()
        audit_event_id = self.uuid_factory()

        encrypted = await self.content_encryption.encrypt_and_persist(
            uow,
            content_id=content_id,
            tenant_id=batch.tenant_id,
            kind=EncryptedContentKind.RAW_MESSAGE,
            encoding=ContentEncoding.UTF8,
            plaintext=message_text,
            created_at=occurred_at,
        )
        message = Message(
            id=message_id,
            tenant_id=batch.tenant_id,
            conversation_thread_id=thread.id,
            external_message_id=external_message_id,
            sender_type=sender_type,
            direction=direction,
            sent_at=sent_at,
            received_at=received_at,
            content_id=content_id,
            reply_to_message_id=reply_to_message_id,
            adapter_metadata=AdapterMetadata.from_mapping({"source": "csv_import"}),
        )
        try:
            await uow.messages.append(message)
        except DuplicateMessageError:
            return 1, 0

        await uow.outbox_jobs.enqueue(
            build_outbox_job(
                job_id=outbox_job_id,
                tenant_id=batch.tenant_id,
                job_kind=OutboxJobKind.CONTENT_REDACT,
                reference=OutboxJobReference(
                    resource_type="message",
                    resource_id=message_id,
                    schema_version=1,
                    tenant_id=batch.tenant_id,
                    secondary_id=content_id,
                ),
                deduplication_key=_content_redact_deduplication_key(resource_id=message_id),
                created_at=occurred_at,
            )
        )
        await append_required_audit_event(
            uow.audit_events,
            raw_message_stored_event(
                tenant_id=batch.tenant_id,
                message_id=message_id,
                content_id=content_id,
                key_version=encrypted.key_version,
                occurred_at=occurred_at,
                audit_context=audit_context,
                actor_type=AuditActorType.SERVICE,
                actor_id=self.service_actor_id,
                event_id=audit_event_id,
            ),
        )
        return 1, 0

    async def _record_row_error(
        self,
        *,
        uow: IntegratedUnitOfWork,
        batch: CsvImportBatch,
        row_number: int,
        error_code: CsvImportErrorCode,
        occurred_at: datetime,
    ) -> None:
        await uow.csv_import_row_errors.append(
            CsvImportRowError(
                import_id=batch.id,
                row_number=row_number,
                error_code=error_code,
                occurred_at=occurred_at,
            )
        )

    async def _get_or_create_thread(
        self,
        *,
        uow: IntegratedUnitOfWork,
        batch: CsvImportBatch,
        external_conversation_id: str,
        occurred_at: datetime,
    ) -> ConversationThread:
        existing = await uow.conversation_threads.get_by_external_conversation_id(
            tenant_id=batch.tenant_id,
            channel_connection_id=batch.channel_connection_id,
            external_conversation_id=external_conversation_id,
        )
        if existing is not None:
            return existing

        thread = ConversationThread(
            id=self.uuid_factory(),
            tenant_id=batch.tenant_id,
            channel_connection_id=batch.channel_connection_id,
            external_conversation_id=external_conversation_id,
            sales_case_id=None,
            lifecycle_status=None,
            adapter_metadata=AdapterMetadata.from_mapping({"source": "csv_import"}),
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        await uow.conversation_threads.add(thread)
        return thread


def _load_data_rows(
    *,
    csv_bytes: bytes,
    delimiter: CsvDelimiter,
    source_encoding: CsvSourceEncoding,
) -> tuple[tuple[str, ...], ...]:
    if source_encoding is CsvSourceEncoding.UTF8_BOM:
        text = csv_bytes.decode("utf-8-sig")
    else:
        text = csv_bytes.decode("utf-8")

    reader = csv.reader(io.StringIO(text), delimiter=_DELIMITER_MAP[delimiter])
    next(reader, None)
    rows: list[tuple[str, ...]] = []
    for row in reader:
        if not row or all(not cell.strip() for cell in row):
            continue
        rows.append(tuple(row))
    return tuple(rows)


def _extract_row_values(*, row: tuple[str, ...], mapping: CsvColumnMapping) -> dict[str, str]:
    values: dict[str, str] = {}
    for field_name, column_index in mapping.field_indexes:
        if column_index >= len(row):
            raise ValueError("row is missing mapped column")
        value = row[column_index].strip()
        if not value:
            raise ValueError("mapped value is empty")
        values[field_name] = value
    return values


def _parse_timestamp(value: str, *, field_name: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed
