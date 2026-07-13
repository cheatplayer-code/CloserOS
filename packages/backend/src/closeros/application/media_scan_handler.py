"""Outbox handler for media.scan jobs."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from uuid import UUID

from closeros.application.audit_recording import AuditContext
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.media_scan_ports import MediaScanner, MediaScanVerdict
from closeros.domain.audit import AuditActorType
from closeros.domain.encrypted_content import ContentAccessPurpose
from closeros.domain.outbox import OutboxErrorCode, OutboxJob
from closeros.domain.provider_media_reference import MediaQuarantineStatus

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_SCAN_CHUNK_SIZE_BYTES = 64 * 1024


class MediaScanHandlerError(Exception):
    def __init__(self, *, error_code: OutboxErrorCode, permanent: bool) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("media scan failed")


class MediaScanHandler:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        media_scanner: MediaScanner,
        content_encryption: ContentEncryptionService,
        service_actor_id: UUID,
        uuid_factory: _UuidFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._media_scanner = media_scanner
        self._content_encryption = content_encryption
        self._service_actor_id = service_actor_id
        self._uuid_factory = uuid_factory

    async def handle(self, *, job: OutboxJob) -> None:
        if job.tenant_id is None:
            raise MediaScanHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )
        reference = job.reference
        if reference.resource_type != "provider_media_reference":
            raise MediaScanHandlerError(
                error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                permanent=True,
            )

        uow = self._uow_factory()
        async with uow:
            record = await uow.provider_media_references.get_by_id(
                tenant_id=job.tenant_id,
                media_reference_id=reference.resource_id,
            )
            if record is None:
                raise MediaScanHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )
            await uow.provider_media_references.update_status(
                tenant_id=job.tenant_id,
                media_reference_id=record.id,
                quarantine_status=MediaQuarantineStatus.SCANNING,
                updated_at=job.created_at,
            )
            await uow.commit()

        if record.encrypted_content_id is None:
            raise MediaScanHandlerError(
                error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                permanent=True,
            )

        decrypted = await self._content_encryption.load_and_decrypt(
            tenant_id=job.tenant_id,
            content_id=record.encrypted_content_id,
            purpose=ContentAccessPurpose.MEDIA_SCAN,
            occurred_at=job.created_at,
            audit_context=AuditContext(correlation_id=job.id),
            actor_type=AuditActorType.SERVICE,
            actor_id=self._service_actor_id,
            audit_event_id=self._uuid_factory(),
        )

        plaintext = decrypted.as_bytes()

        def chunk_plaintext() -> Iterator[bytes]:
            for offset in range(0, len(plaintext), _SCAN_CHUNK_SIZE_BYTES):
                yield plaintext[offset : offset + _SCAN_CHUNK_SIZE_BYTES]

        scan_result = await self._media_scanner.scan_chunks(chunks=chunk_plaintext())
        if scan_result.verdict is MediaScanVerdict.SCAN_UNAVAILABLE:
            raise MediaScanHandlerError(
                error_code=OutboxErrorCode.ADAPTER_UNAVAILABLE,
                permanent=False,
            )
        if scan_result.verdict is MediaScanVerdict.INFECTED:
            final_status = MediaQuarantineStatus.INFECTED
            delete_content = True
            clear_encrypted_content_id = True
        else:
            final_status = MediaQuarantineStatus.CLEAN
            delete_content = False
            clear_encrypted_content_id = False

        uow = self._uow_factory()
        async with uow:
            if delete_content:
                await uow.encrypted_contents.delete(
                    tenant_id=job.tenant_id,
                    content_id=record.encrypted_content_id,
                )
            await uow.provider_media_references.update_status(
                tenant_id=job.tenant_id,
                media_reference_id=record.id,
                quarantine_status=final_status,
                updated_at=job.created_at,
                clear_encrypted_content_id=clear_encrypted_content_id,
            )
            await uow.commit()


__all__ = ["MediaScanHandler", "MediaScanHandlerError"]
