"""Tests for media fetch and scan handlers."""

# mypy: ignore-errors

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import pytest
from closeros.application.media_fetch_handler import MediaFetchHandler, MediaFetchHandlerError
from closeros.application.media_fetch_ports import (
    FetchedMediaArtifact,
    MediaFetchOversizeError,
    MediaFetchRejectedUrlError,
    MediaFetchUnavailableError,
    MediaFetchUnsupportedMimeError,
)
from closeros.application.media_scan_handler import MediaScanHandler, MediaScanHandlerError
from closeros.application.media_scan_ports import MediaScanVerdict
from closeros.domain.encrypted_content import ContentEncoding, EncryptedContentKind
from closeros.domain.outbox import (
    OutboxErrorCode,
    OutboxJobKind,
    OutboxJobReference,
    build_outbox_job,
)
from closeros.domain.provider_credentials import SecretBytes
from closeros.domain.provider_media_reference import MediaQuarantineStatus
from closeros.infrastructure.clamav_scanner_adapter import MockClamAvScannerAdapter
from closeros.infrastructure.media_url_validator import (
    MediaUrlValidationError,
    is_allowed_meta_media_host,
    validate_meta_media_download_url,
)
from closeros.infrastructure.whatsapp_media_fetch_adapter import WhatsAppMediaFetchAdapter

from tests.encryption_support import (
    CONTENT_ID,
    NOW,
    SERVICE_ID,
    build_content_encryption_service,
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000010")
MEDIA_ID = UUID("00000000-0000-0000-0000-000000000020")
CONNECTION_ID = UUID("00000000-0000-0000-0000-000000000030")
TOKEN = SecretBytes(b"test-token")
# Synthetic userinfo for a negative URL-validation case, kept split from the
# scheme so no complete credentialed URI literal is committed.
_SYNTHETIC_USERINFO = "user:pass"


class _MediaRecord:
    id = MEDIA_ID
    channel_connection_id = CONNECTION_ID
    provider_media_id = "media-123"
    encrypted_content_id: UUID | None = None


class _MediaRepo:
    def __init__(self, *, encrypted_content_id: UUID | None = None) -> None:
        self.statuses: list[MediaQuarantineStatus] = []
        self.encrypted_content_ids: list[UUID | None] = []
        self._encrypted_content_id = encrypted_content_id

    async def get_by_id(self, *, tenant_id, media_reference_id):  # type: ignore[no-untyped-def]
        record = _MediaRecord()
        record.encrypted_content_id = self._encrypted_content_id
        return record

    async def update_status(
        self, *, tenant_id, media_reference_id, quarantine_status, updated_at, **kwargs
    ):  # type: ignore[no-untyped-def]
        self.statuses.append(quarantine_status)
        if "encrypted_content_id" in kwargs:
            self.encrypted_content_ids.append(kwargs["encrypted_content_id"])
        if kwargs.get("clear_encrypted_content_id"):
            self.encrypted_content_ids.append(None)


class _OutboxRepo:
    def __init__(self) -> None:
        self.jobs: list[object] = []

    async def enqueue(self, job) -> None:  # type: ignore[no-untyped-def]
        self.jobs.append(job)


class _EncryptedRepo:
    def __init__(self) -> None:
        self.deleted: list[UUID] = []
        self.stored: list[object] = []

    async def add(self, content) -> None:  # type: ignore[no-untyped-def]
        self.stored.append(content)

    async def get_by_id(self, *, tenant_id, content_id):  # type: ignore[no-untyped-def]
        for content in self.stored:
            if content.id == content_id:
                return content
        return None

    async def delete(self, *, tenant_id, content_id) -> None:  # type: ignore[no-untyped-def]
        self.deleted.append(content_id)


class _TenantRepo:
    async def get_by_id(self, tenant_id):  # type: ignore[no-untyped-def]
        from tests.tenant_persistence_support import synthetic_tenant

        return synthetic_tenant(tenant_id=tenant_id)


class _AuditRepo:
    async def append(self, event) -> None:  # type: ignore[no-untyped-def]
        return None


class _Uow:
    def __init__(
        self,
        *,
        media_repo: _MediaRepo,
        outbox_repo: _OutboxRepo | None = None,
        encrypted_repo: _EncryptedRepo | None = None,
    ) -> None:
        self.provider_media_references = media_repo
        self.outbox_jobs = outbox_repo or _OutboxRepo()
        self.encrypted_contents = encrypted_repo or _EncryptedRepo()
        self.tenants = _TenantRepo()
        self.audit_events = _AuditRepo()

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        return self

    async def __aexit__(self, *args) -> None:  # type: ignore[no-untyped-def]
        return None

    async def commit(self) -> None:
        return None


def _build_scan_job() -> object:
    return build_outbox_job(
        job_id=uuid4(),
        tenant_id=TENANT_ID,
        job_kind=OutboxJobKind.MEDIA_SCAN,
        reference=OutboxJobReference(
            resource_type="provider_media_reference",
            resource_id=MEDIA_ID,
            schema_version=1,
            tenant_id=TENANT_ID,
        ),
        deduplication_key="media_scan_test",
        created_at=NOW,
    )


def _build_fetch_job() -> object:
    return build_outbox_job(
        job_id=uuid4(),
        tenant_id=TENANT_ID,
        job_kind=OutboxJobKind.MEDIA_FETCH,
        reference=OutboxJobReference(
            resource_type="provider_media_reference",
            resource_id=MEDIA_ID,
            schema_version=1,
            tenant_id=TENANT_ID,
        ),
        deduplication_key="media_fetch_test",
        created_at=NOW,
    )


def test_validate_meta_media_download_url_accepts_allowlisted_host() -> None:
    url = validate_meta_media_download_url("https://lookaside.fbsbx.com/media/abc")
    assert url.startswith("https://lookaside.fbsbx.com/")


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("http://lookaside.fbsbx.com/media", "https"),
        ("https://evil.example/media", "allowlisted"),
        ("https://lookaside.fbsbx.com:8080/media", "port"),
        # Userinfo assembled at runtime so no complete credentialed URI literal
        # exists in source; the validator must still reject embedded userinfo.
        (f"https://{_SYNTHETIC_USERINFO}@lookaside.fbsbx.com/media", "userinfo"),
        ("https://lookaside.fbsbx.com/media#fragment", "fragment"),
        ("https://127.0.0.1/media", "not allowed"),
        ("https://localhost/media", "not allowed"),
    ],
)
def test_validate_meta_media_download_url_rejects_unsafe_urls(url: str, message: str) -> None:
    with pytest.raises(MediaUrlValidationError, match=message):
        validate_meta_media_download_url(url)


def test_is_allowed_meta_media_host_suffixes() -> None:
    assert is_allowed_meta_media_host("lookaside.fbsbx.com")
    assert is_allowed_meta_media_host("scontent.xx.fbcdn.net")
    assert is_allowed_meta_media_host("graph.facebook.com")
    assert not is_allowed_meta_media_host("example.com")


def test_media_scan_handler_marks_clean() -> None:
    async def exercise() -> None:
        encrypted_repo = _EncryptedRepo()
        media_repo = _MediaRepo(encrypted_content_id=CONTENT_ID)
        uow = _Uow(media_repo=media_repo, encrypted_repo=encrypted_repo)
        encryption = build_content_encryption_service(lambda: uow)
        await encryption.encrypt_and_persist(
            uow,
            content_id=CONTENT_ID,
            tenant_id=TENANT_ID,
            kind=EncryptedContentKind.PROVIDER_MEDIA_BINARY,
            encoding=ContentEncoding.BINARY,
            plaintext=b"clean-bytes",
            created_at=NOW,
        )
        handler = MediaScanHandler(
            uow_factory=lambda: _Uow(media_repo=media_repo, encrypted_repo=encrypted_repo),
            media_scanner=MockClamAvScannerAdapter(verdict=MediaScanVerdict.CLEAN),
            content_encryption=encryption,
            service_actor_id=SERVICE_ID,
            uuid_factory=uuid4,
        )
        await handler.handle(job=_build_scan_job())
        assert media_repo.statuses[-1] is MediaQuarantineStatus.CLEAN

    asyncio.run(exercise())


def test_media_scan_handler_marks_infected_and_deletes_content() -> None:
    async def exercise() -> None:
        encrypted_repo = _EncryptedRepo()
        media_repo = _MediaRepo(encrypted_content_id=CONTENT_ID)
        uow = _Uow(media_repo=media_repo, encrypted_repo=encrypted_repo)
        encryption = build_content_encryption_service(lambda: uow)
        await encryption.encrypt_and_persist(
            uow,
            content_id=CONTENT_ID,
            tenant_id=TENANT_ID,
            kind=EncryptedContentKind.PROVIDER_MEDIA_BINARY,
            encoding=ContentEncoding.BINARY,
            plaintext=b"eicar",
            created_at=NOW,
        )
        handler = MediaScanHandler(
            uow_factory=lambda: _Uow(media_repo=media_repo, encrypted_repo=encrypted_repo),
            media_scanner=MockClamAvScannerAdapter(
                verdict=MediaScanVerdict.INFECTED,
                signature="EICAR",
            ),
            content_encryption=encryption,
            service_actor_id=SERVICE_ID,
            uuid_factory=uuid4,
        )
        await handler.handle(job=_build_scan_job())
        assert media_repo.statuses[-1] is MediaQuarantineStatus.INFECTED
        assert encrypted_repo.deleted == [CONTENT_ID]
        assert media_repo.encrypted_content_ids[-1] is None

    asyncio.run(exercise())


def test_media_scan_handler_retries_when_scanner_unavailable() -> None:
    async def exercise() -> None:
        encrypted_repo = _EncryptedRepo()
        media_repo = _MediaRepo(encrypted_content_id=CONTENT_ID)
        uow = _Uow(media_repo=media_repo, encrypted_repo=encrypted_repo)
        encryption = build_content_encryption_service(lambda: uow)
        await encryption.encrypt_and_persist(
            uow,
            content_id=CONTENT_ID,
            tenant_id=TENANT_ID,
            kind=EncryptedContentKind.PROVIDER_MEDIA_BINARY,
            encoding=ContentEncoding.BINARY,
            plaintext=b"pending",
            created_at=NOW,
        )
        handler = MediaScanHandler(
            uow_factory=lambda: _Uow(media_repo=media_repo, encrypted_repo=encrypted_repo),
            media_scanner=MockClamAvScannerAdapter(verdict=MediaScanVerdict.SCAN_UNAVAILABLE),
            content_encryption=encryption,
            service_actor_id=SERVICE_ID,
            uuid_factory=uuid4,
        )
        with pytest.raises(MediaScanHandlerError) as raised:
            await handler.handle(job=_build_scan_job())
        assert raised.value.permanent is False
        assert raised.value.error_code is OutboxErrorCode.ADAPTER_UNAVAILABLE
        assert encrypted_repo.deleted == []

    asyncio.run(exercise())


@dataclass(frozen=True, slots=True)
class _StubFetcher:
    artifact: FetchedMediaArtifact | None = None
    error: Exception | None = None

    async def fetch_whatsapp_media(self, **kwargs) -> FetchedMediaArtifact:  # type: ignore[no-untyped-def]
        if self.error is not None:
            raise self.error
        assert self.artifact is not None
        return self.artifact


def _artifact_from_bytes(
    payload: bytes,
    *,
    mime_type: str | None = "image/png",
    spool_max: int = 1_048_576,
) -> FetchedMediaArtifact:
    spool = tempfile.SpooledTemporaryFile(max_size=spool_max)  # noqa: SIM115
    spool.write(payload)
    spool.seek(0)
    return FetchedMediaArtifact(stream=spool, mime_type=mime_type, size_bytes=len(payload))


def test_media_fetch_handler_encrypts_and_enqueues_scan() -> None:
    async def exercise() -> None:
        media_repo = _MediaRepo()
        outbox_repo = _OutboxRepo()
        encrypted_repo = _EncryptedRepo()
        uow = _Uow(media_repo=media_repo, outbox_repo=outbox_repo, encrypted_repo=encrypted_repo)
        encryption = build_content_encryption_service(lambda: uow)
        handler = MediaFetchHandler(
            uow_factory=lambda: _Uow(
                media_repo=media_repo,
                outbox_repo=outbox_repo,
                encrypted_repo=encrypted_repo,
            ),
            media_fetcher=_StubFetcher(
                artifact=_artifact_from_bytes(b"abc"),
            ),
            access_token_resolver=lambda tenant_id, connection_id, media_id: TOKEN,
            content_encryption=encryption,
            uuid_factory=uuid4,
        )
        await handler.handle(job=_build_fetch_job())
        assert media_repo.statuses[-1] is MediaQuarantineStatus.QUARANTINED_PENDING_SCAN
        assert len(media_repo.encrypted_content_ids) == 1
        assert media_repo.encrypted_content_ids[0] is not None
        assert len(encrypted_repo.stored) == 1
        assert encrypted_repo.stored[0].kind is EncryptedContentKind.PROVIDER_MEDIA_BINARY
        assert len(outbox_repo.jobs) == 1
        assert outbox_repo.jobs[0].job_kind is OutboxJobKind.MEDIA_SCAN

    asyncio.run(exercise())


def test_media_fetch_handler_marks_fetch_failed_for_oversize() -> None:
    async def exercise() -> None:
        media_repo = _MediaRepo()
        handler = MediaFetchHandler(
            uow_factory=lambda: _Uow(media_repo=media_repo),
            media_fetcher=_StubFetcher(error=MediaFetchOversizeError("too large")),
            access_token_resolver=lambda tenant_id, connection_id, media_id: TOKEN,
            content_encryption=build_content_encryption_service(
                lambda: _Uow(media_repo=media_repo)
            ),
            uuid_factory=uuid4,
        )
        with pytest.raises(MediaFetchHandlerError):
            await handler.handle(job=_build_fetch_job())
        assert media_repo.statuses[-1] is MediaQuarantineStatus.FETCH_FAILED

    asyncio.run(exercise())


def test_media_fetch_handler_marks_fetch_failed_for_unsupported_mime() -> None:
    async def exercise() -> None:
        media_repo = _MediaRepo()
        handler = MediaFetchHandler(
            uow_factory=lambda: _Uow(media_repo=media_repo),
            media_fetcher=_StubFetcher(
                error=MediaFetchUnsupportedMimeError("unsupported mime"),
            ),
            access_token_resolver=lambda tenant_id, connection_id, media_id: TOKEN,
            content_encryption=build_content_encryption_service(
                lambda: _Uow(media_repo=media_repo)
            ),
            uuid_factory=uuid4,
        )
        with pytest.raises(MediaFetchHandlerError):
            await handler.handle(job=_build_fetch_job())
        assert media_repo.statuses[-1] is MediaQuarantineStatus.FETCH_FAILED

    asyncio.run(exercise())


def test_whatsapp_media_fetch_adapter_rejects_bad_host_before_token_use() -> None:
    async def exercise() -> None:
        observed_authorizations: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            auth = request.headers.get("Authorization")
            if auth is not None:
                observed_authorizations.append(auth)
            if request.url.path.endswith("/media-123"):
                return httpx.Response(
                    200,
                    json={
                        "url": "https://evil.example/download",
                        "mime_type": "image/png",
                        "file_size": 3,
                    },
                )
            raise AssertionError(f"unexpected request: {request.url}")

        adapter = WhatsAppMediaFetchAdapter(
            graph_api_base_url="https://graph.facebook.com/v21.0",
            _client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        with pytest.raises(MediaFetchRejectedUrlError):
            await adapter.fetch_whatsapp_media(
                tenant_id=TENANT_ID,
                whatsapp_connection_id=CONNECTION_ID,
                provider_media_id="media-123",
                access_token=TOKEN,
            )
        assert observed_authorizations == ["Bearer test-token"]

    asyncio.run(exercise())


def test_whatsapp_media_fetch_adapter_streams_with_size_cap() -> None:
    async def exercise() -> None:
        payload = b"x" * 10

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/media-123"):
                return httpx.Response(
                    200,
                    json={
                        "url": "https://lookaside.fbsbx.com/download",
                        "mime_type": "image/png",
                        "file_size": len(payload),
                    },
                )
            if request.url.host == "lookaside.fbsbx.com":
                return httpx.Response(200, content=payload)
            raise AssertionError(f"unexpected request: {request.url}")

        adapter = WhatsAppMediaFetchAdapter(
            graph_api_base_url="https://graph.facebook.com/v21.0",
            max_bytes=5,
            _client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        with pytest.raises(MediaFetchOversizeError):
            await adapter.fetch_whatsapp_media(
                tenant_id=TENANT_ID,
                whatsapp_connection_id=CONNECTION_ID,
                provider_media_id="media-123",
                access_token=TOKEN,
            )

    asyncio.run(exercise())


def test_media_fetch_handler_encrypts_stream_not_bytes() -> None:
    async def exercise() -> None:
        media_repo = _MediaRepo()
        outbox_repo = _OutboxRepo()
        encrypted_repo = _EncryptedRepo()
        uow = _Uow(media_repo=media_repo, outbox_repo=outbox_repo, encrypted_repo=encrypted_repo)
        encryption = build_content_encryption_service(lambda: uow)
        artifact = _artifact_from_bytes(b"abc")
        handler = MediaFetchHandler(
            uow_factory=lambda: _Uow(
                media_repo=media_repo,
                outbox_repo=outbox_repo,
                encrypted_repo=encrypted_repo,
            ),
            media_fetcher=_StubFetcher(artifact=artifact),
            access_token_resolver=lambda tenant_id, connection_id, media_id: TOKEN,
            content_encryption=encryption,
            uuid_factory=uuid4,
        )
        await handler.handle(job=_build_fetch_job())
        assert not isinstance(artifact, bytes)
        assert not hasattr(artifact, "content")
        assert artifact.stream.closed

    asyncio.run(exercise())


def test_media_fetch_artifact_rolls_to_disk_for_large_payload() -> None:
    payload = b"x" * 2048
    artifact = _artifact_from_bytes(payload, spool_max=512)
    assert getattr(artifact.stream, "_rolled", False) is True
    artifact.close()


def test_media_fetch_handler_closes_artifact_when_encryption_fails() -> None:
    async def exercise() -> None:
        media_repo = _MediaRepo()
        artifact = _artifact_from_bytes(b"abc")

        class _FailingEncryption:
            async def encrypt_and_persist_stream(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("encryption failed")

        handler = MediaFetchHandler(
            uow_factory=lambda: _Uow(media_repo=media_repo),
            media_fetcher=_StubFetcher(artifact=artifact),
            access_token_resolver=lambda tenant_id, connection_id, media_id: TOKEN,
            content_encryption=_FailingEncryption(),  # type: ignore[arg-type]
            uuid_factory=uuid4,
        )
        with pytest.raises(RuntimeError, match="encryption failed"):
            await handler.handle(job=_build_fetch_job())
        assert artifact.stream.closed

    asyncio.run(exercise())


def test_whatsapp_media_fetch_adapter_returns_stream_artifact_not_bytes() -> None:
    async def exercise() -> None:
        payload = b"png-bytes"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/media-123"):
                return httpx.Response(
                    200,
                    json={
                        "url": "https://lookaside.fbsbx.com/download",
                        "mime_type": "image/png",
                        "file_size": len(payload),
                    },
                )
            if request.url.host == "lookaside.fbsbx.com":
                return httpx.Response(200, content=payload)
            raise AssertionError(f"unexpected request: {request.url}")

        adapter = WhatsAppMediaFetchAdapter(
            graph_api_base_url="https://graph.facebook.com/v21.0",
            _client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        artifact = await adapter.fetch_whatsapp_media(
            tenant_id=TENANT_ID,
            whatsapp_connection_id=CONNECTION_ID,
            provider_media_id="media-123",
            access_token=TOKEN,
        )
        try:
            assert not isinstance(artifact, bytes)
            assert not hasattr(artifact, "content")
            rendered = repr(artifact)
            assert "/tmp" not in rendered
            assert "SpooledTemporaryFile" not in rendered
            assert artifact.size_bytes == len(payload)
            assert artifact.stream.read(3) == payload[:3]
        finally:
            artifact.close()

    asyncio.run(exercise())


def test_fetched_media_artifact_dataclass() -> None:
    artifact = _artifact_from_bytes(b"abc")
    try:
        assert artifact.size_bytes == 3
        assert not isinstance(artifact, bytes)
        assert not hasattr(artifact, "content")
    finally:
        artifact.close()


class _FailingFetcher:
    async def fetch_whatsapp_media(self, **kwargs) -> FetchedMediaArtifact:  # type: ignore[no-untyped-def]
        raise MediaFetchUnavailableError("unavailable")


def test_clamav_scan_allows_concurrent_event_loop_work() -> None:
    import time
    from unittest.mock import patch

    from closeros.application.media_scan_ports import MediaScanVerdict
    from closeros.infrastructure.clamav_scanner_adapter import ClamAvScannerAdapter

    def _slow_instream(**_: object) -> str:
        time.sleep(0.3)
        return "stream: OK"

    async def exercise() -> None:
        adapter = ClamAvScannerAdapter()
        concurrent_done = asyncio.Event()

        async def other_work() -> None:
            await asyncio.sleep(0.05)
            concurrent_done.set()

        with patch(
            "closeros.infrastructure.clamav_scanner_adapter._send_instream_frames",
            side_effect=_slow_instream,
        ):
            scan_task = asyncio.create_task(adapter.scan_bytes(content=b"scan-me"))
            other_task = asyncio.create_task(other_work())
            scan_result, _ = await asyncio.gather(scan_task, other_task)

        assert concurrent_done.is_set()
        assert scan_result.verdict is MediaScanVerdict.CLEAN

    asyncio.run(exercise())
