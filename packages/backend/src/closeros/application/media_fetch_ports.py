"""Application ports for provider media fetch."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import BinaryIO, Protocol
from uuid import UUID

from closeros.domain.provider_credentials import SecretBytes


class MediaFetchError(Exception):
    """Base class for safe media fetch failures."""


class MediaFetchUnavailableError(MediaFetchError):
    """Raised when media cannot be fetched from the provider."""


class MediaFetchFailedError(MediaFetchError):
    """Raised when media fetch fails permanently (oversize, mime, rejected URL)."""


class MediaFetchOversizeError(MediaFetchFailedError):
    """Raised when provider media exceeds the configured size limit."""


class MediaFetchUnsupportedMimeError(MediaFetchFailedError):
    """Raised when provider media mime type is not supported."""


class MediaFetchRejectedUrlError(MediaFetchFailedError):
    """Raised when a provider media download URL fails safety validation."""


@dataclass(slots=True)
class FetchedMediaArtifact:
    """Bounded spooled plaintext media owned by the fetcher until closed."""

    stream: BinaryIO = field(repr=False)
    mime_type: str | None
    size_bytes: int

    def close(self) -> None:
        self.stream.close()


class MediaFetcher(Protocol):
    async def fetch_whatsapp_media(
        self,
        *,
        tenant_id: UUID,
        whatsapp_connection_id: UUID,
        provider_media_id: str,
        access_token: SecretBytes,
    ) -> FetchedMediaArtifact: ...


__all__ = [
    "FetchedMediaArtifact",
    "MediaFetchError",
    "MediaFetchFailedError",
    "MediaFetcher",
    "MediaFetchOversizeError",
    "MediaFetchRejectedUrlError",
    "MediaFetchUnavailableError",
    "MediaFetchUnsupportedMimeError",
]
