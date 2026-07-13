"""Outbox handler for media.fetch jobs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from inspect import isawaitable
from uuid import UUID

from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.media_fetch_ports import (
    MediaFetcher,
    MediaFetchFailedError,
    MediaFetchUnavailableError,
)
from closeros.application.provider_media_persistence import ProviderMediaReferenceRecord
from closeros.domain.encrypted_content import (
    ContentEncoding,
    EncryptedContentKind,
)
from closeros.domain.outbox import (
    OutboxErrorCode,
    OutboxJob,
    OutboxJobKind,
    OutboxJobReference,
    build_outbox_job,
)
from closeros.domain.provider_media_reference import MediaQuarantineStatus

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_AccessTokenResolver = Callable[
    [UUID, UUID, UUID],
    object | None | Awaitable[object | None],
]


class MediaFetchHandlerError(Exception):
    def __init__(self, *, error_code: OutboxErrorCode, permanent: bool) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("media fetch failed")


class MediaFetchHandler:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        media_fetcher: MediaFetcher,
        access_token_resolver: _AccessTokenResolver,
        content_encryption: ContentEncryptionService,
        uuid_factory: _UuidFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._media_fetcher = media_fetcher
        self._access_token_resolver = access_token_resolver
        self._content_encryption = content_encryption
        self._uuid_factory = uuid_factory

    async def handle(self, *, job: OutboxJob) -> None:
        tenant_id = job.tenant_id
        if tenant_id is None:
            raise MediaFetchHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )
        reference = job.reference
        if reference.resource_type != "provider_media_reference":
            raise MediaFetchHandlerError(
                error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                permanent=True,
            )

        uow = self._uow_factory()
        async with uow:
            record = await uow.provider_media_references.get_by_id(
                tenant_id=tenant_id,
                media_reference_id=reference.resource_id,
            )
            if record is None:
                raise MediaFetchHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )
            await uow.provider_media_references.update_status(
                tenant_id=tenant_id,
                media_reference_id=record.id,
                quarantine_status=MediaQuarantineStatus.FETCHING,
                updated_at=job.created_at,
            )
            await uow.commit()

        access_token_result = self._access_token_resolver(
            tenant_id,
            record.channel_connection_id,
            record.id,
        )
        access_token = (
            await access_token_result if isawaitable(access_token_result) else access_token_result
        )
        if access_token is None:
            await self._mark_fetch_unavailable(
                tenant_id=tenant_id,
                job=job,
                record=record,
            )
            raise MediaFetchHandlerError(
                error_code=OutboxErrorCode.ADAPTER_UNAVAILABLE,
                permanent=True,
            )

        try:
            artifact = await self._media_fetcher.fetch_whatsapp_media(
                tenant_id=tenant_id,
                whatsapp_connection_id=record.channel_connection_id,
                provider_media_id=record.provider_media_id,
                access_token=access_token,  # type: ignore[arg-type]
            )
        except MediaFetchFailedError as exc:
            await self._mark_fetch_failed(
                tenant_id=tenant_id,
                job=job,
                record=record,
            )
            raise MediaFetchHandlerError(
                error_code=OutboxErrorCode.ADAPTER_UNAVAILABLE,
                permanent=True,
            ) from exc
        except MediaFetchUnavailableError as exc:
            await self._mark_fetch_unavailable(
                tenant_id=tenant_id,
                job=job,
                record=record,
            )
            raise MediaFetchHandlerError(
                error_code=OutboxErrorCode.ADAPTER_UNAVAILABLE,
                permanent=False,
            ) from exc

        encrypted_content_id = self._uuid_factory()
        scan_job_id = self._uuid_factory()
        occurred_at = job.processing_started_at or job.created_at
        try:
            uow = self._uow_factory()
            async with uow:
                await self._content_encryption.encrypt_and_persist_stream(
                    uow,
                    content_id=encrypted_content_id,
                    tenant_id=tenant_id,
                    kind=EncryptedContentKind.PROVIDER_MEDIA_BINARY,
                    encoding=ContentEncoding.BINARY,
                    stream=artifact.stream,
                    plaintext_byte_length=artifact.size_bytes,
                    created_at=occurred_at,
                )
                await uow.provider_media_references.update_status(
                    tenant_id=tenant_id,
                    media_reference_id=record.id,
                    quarantine_status=MediaQuarantineStatus.QUARANTINED_PENDING_SCAN,
                    updated_at=occurred_at,
                    mime_type=artifact.mime_type,
                    size_bytes=artifact.size_bytes,
                    encrypted_content_id=encrypted_content_id,
                )
                await uow.outbox_jobs.enqueue(
                    build_outbox_job(
                        job_id=scan_job_id,
                        tenant_id=tenant_id,
                        job_kind=OutboxJobKind.MEDIA_SCAN,
                        reference=OutboxJobReference(
                            resource_type="provider_media_reference",
                            resource_id=record.id,
                            schema_version=1,
                            tenant_id=tenant_id,
                            secondary_id=reference.secondary_id,
                        ),
                        deduplication_key=f"media_scan_{record.id}",
                        created_at=occurred_at,
                    )
                )
                await uow.commit()
        finally:
            artifact.close()

    async def _mark_fetch_failed(
        self,
        *,
        tenant_id: UUID,
        job: OutboxJob,
        record: ProviderMediaReferenceRecord,
    ) -> None:
        uow = self._uow_factory()
        async with uow:
            await uow.provider_media_references.update_status(
                tenant_id=tenant_id,
                media_reference_id=record.id,
                quarantine_status=MediaQuarantineStatus.FETCH_FAILED,
                updated_at=job.created_at,
            )
            await uow.commit()

    async def _mark_fetch_unavailable(
        self,
        *,
        tenant_id: UUID,
        job: OutboxJob,
        record: ProviderMediaReferenceRecord,
    ) -> None:
        uow = self._uow_factory()
        async with uow:
            await uow.provider_media_references.update_status(
                tenant_id=tenant_id,
                media_reference_id=record.id,
                quarantine_status=MediaQuarantineStatus.FETCH_UNAVAILABLE,
                updated_at=job.created_at,
            )
            await uow.commit()


__all__ = ["MediaFetchHandler", "MediaFetchHandlerError"]
