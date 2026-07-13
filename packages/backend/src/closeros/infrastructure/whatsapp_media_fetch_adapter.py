"""WhatsApp Cloud media fetch adapter."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from typing import BinaryIO, cast
from uuid import UUID

import httpx

from closeros.application.media_fetch_ports import (
    FetchedMediaArtifact,
    MediaFetchOversizeError,
    MediaFetchRejectedUrlError,
    MediaFetchUnavailableError,
    MediaFetchUnsupportedMimeError,
)
from closeros.domain.encrypted_content import PROVIDER_MEDIA_BINARY_MAX_PLAINTEXT_BYTES
from closeros.domain.provider_credentials import SecretBytes
from closeros.domain.provider_media_reference import is_supported_provider_media_mime
from closeros.infrastructure.media_url_validator import (
    MediaUrlValidationError,
    validate_meta_media_download_url,
)

_STREAM_CHUNK_SIZE_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class WhatsAppMediaFetchAdapter:
    graph_api_base_url: str = "https://graph.facebook.com/v21.0"
    timeout_seconds: float = 30.0
    max_bytes: int = PROVIDER_MEDIA_BINARY_MAX_PLAINTEXT_BYTES
    _client: httpx.AsyncClient | None = None

    async def fetch_whatsapp_media(
        self,
        *,
        tenant_id: UUID,
        whatsapp_connection_id: UUID,
        provider_media_id: str,
        access_token: SecretBytes,
    ) -> FetchedMediaArtifact:
        _ = tenant_id, whatsapp_connection_id
        if not provider_media_id.strip():
            raise MediaFetchUnavailableError("provider media id is missing")

        token = access_token.value.decode("utf-8")
        metadata_url = f"{self.graph_api_base_url.rstrip('/')}/{provider_media_id}"
        auth_headers = {"Authorization": f"Bearer {token}"}

        try:
            async with self._open_client() as client:
                metadata_response = await client.get(metadata_url, headers=auth_headers)
                if metadata_response.status_code >= 400:
                    raise MediaFetchUnavailableError("provider media metadata unavailable")

                metadata = metadata_response.json()
                if not isinstance(metadata, dict):
                    raise MediaFetchUnavailableError("provider media metadata is invalid")

                download_url = metadata.get("url")
                mime_type = metadata.get("mime_type")
                size_bytes = metadata.get("file_size")
                if not isinstance(download_url, str) or not download_url:
                    raise MediaFetchUnavailableError("provider media download url is missing")

                resolved_mime = mime_type.strip().lower() if isinstance(mime_type, str) else None
                if resolved_mime is not None and not is_supported_provider_media_mime(
                    resolved_mime
                ):
                    raise MediaFetchUnsupportedMimeError(
                        "provider media mime type is not supported"
                    )

                try:
                    validated_download_url = validate_meta_media_download_url(download_url)
                except MediaUrlValidationError as exc:
                    raise MediaFetchRejectedUrlError(
                        "provider media download url is rejected"
                    ) from exc

                artifact = await self._stream_download(
                    client=client,
                    download_url=validated_download_url,
                    headers=auth_headers,
                )
        except MediaFetchUnsupportedMimeError:
            raise
        except MediaFetchRejectedUrlError:
            raise
        except MediaFetchOversizeError:
            raise
        except httpx.HTTPError as exc:
            raise MediaFetchUnavailableError("provider media fetch failed") from exc

        resolved_size = artifact.size_bytes if not isinstance(size_bytes, int) else size_bytes
        return FetchedMediaArtifact(
            stream=artifact.stream,
            mime_type=resolved_mime,
            size_bytes=resolved_size,
        )

    def _open_client(self) -> httpx.AsyncClient | _ReusedAsyncClient:
        if self._client is not None:
            return _ReusedAsyncClient(self._client)
        return httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=False,
        )

    async def _stream_download(
        self,
        *,
        client: httpx.AsyncClient,
        download_url: str,
        headers: dict[str, str],
    ) -> FetchedMediaArtifact:
        spool_max = min(self.max_bytes, 1_048_576)
        total_bytes = 0
        spool = tempfile.SpooledTemporaryFile(max_size=spool_max)  # noqa: SIM115
        try:
            async with client.stream("GET", download_url, headers=headers) as response:
                if response.status_code >= 400:
                    raise MediaFetchUnavailableError("provider media download failed")
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared = int(content_length)
                    except ValueError as exc:
                        raise MediaFetchUnavailableError(
                            "provider media content-length is invalid"
                        ) from exc
                    if declared > self.max_bytes:
                        raise MediaFetchOversizeError("provider media exceeds size limit")
                async for chunk in response.aiter_bytes(chunk_size=_STREAM_CHUNK_SIZE_BYTES):
                    total_bytes += len(chunk)
                    if total_bytes > self.max_bytes:
                        raise MediaFetchOversizeError("provider media exceeds size limit")
                    spool.write(chunk)
            spool.seek(0)
            return FetchedMediaArtifact(
                stream=cast(BinaryIO, spool),
                mime_type=None,
                size_bytes=total_bytes,
            )
        except Exception:
            spool.close()
            raise


class _ReusedAsyncClient:
    """Async context manager that reuses an injected client without closing it."""

    __slots__ = ("_client",)

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *args: object) -> None:
        return None


__all__ = ["WhatsAppMediaFetchAdapter"]
