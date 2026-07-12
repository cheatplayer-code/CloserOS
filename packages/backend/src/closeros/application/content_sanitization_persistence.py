"""Application persistence ports for content sanitization records."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.content_sanitization import ContentSanitization


class ContentSanitizationPersistenceError(PersistenceError):
    """Base class for content sanitization persistence failures."""


class DuplicateContentSanitizationError(ContentSanitizationPersistenceError):
    """Raised when a sanitization row already exists for the same identity."""


class ContentSanitizationNotFoundError(ContentSanitizationPersistenceError):
    """Raised when a sanitization record cannot be found."""


class ContentSanitizationRepository(Protocol):
    async def get_completed_by_source(
        self,
        *,
        tenant_id: UUID,
        source_content_id: UUID,
        policy_version: str,
    ) -> ContentSanitization | None: ...

    async def append_completed(
        self,
        *,
        record: ContentSanitization,
    ) -> None: ...
