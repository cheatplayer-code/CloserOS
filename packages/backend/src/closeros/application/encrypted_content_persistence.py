"""Application-layer persistence ports for encrypted content storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.encrypted_content import (
    EncryptedContent,
    EncryptedContentKind,
    WrappedDataKey,
)


class EncryptedContentPersistenceError(PersistenceError):
    """Base class for safe encrypted-content persistence failures."""


class EncryptedContentRecordNotFoundError(EncryptedContentPersistenceError):
    """Raised when encrypted content does not exist."""


class EncryptedContentReferenceError(EncryptedContentPersistenceError):
    """Raised when a referenced tenant-owned record does not exist."""


class DuplicateEncryptedContentError(EncryptedContentPersistenceError):
    """Raised when encrypted content with the same identifier already exists."""


@dataclass(frozen=True, slots=True)
class EncryptedContentRetentionFilter:
    tenant_id: UUID | None = None
    expires_before: datetime | None = None
    limit: int = 100


class EncryptedContentRepository(Protocol):
    async def add(self, content: EncryptedContent) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
    ) -> EncryptedContent | None: ...

    async def get_for_update(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
    ) -> EncryptedContent | None: ...

    async def replace_wrapped_key(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        wrapped_data_key: WrappedDataKey,
    ) -> None: ...

    async def list_by_tenant_and_kind(
        self,
        *,
        tenant_id: UUID,
        kind: EncryptedContentKind,
        limit: int = 100,
    ) -> tuple[EncryptedContent, ...]: ...

    async def list_due_for_retention(
        self,
        *,
        query_filter: EncryptedContentRetentionFilter,
    ) -> tuple[EncryptedContent, ...]: ...


class EncryptedContentUnitOfWork(Protocol):
    encrypted_contents: EncryptedContentRepository

    async def __aenter__(self) -> EncryptedContentUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
