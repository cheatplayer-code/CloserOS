"""Application-layer repository protocols for knowledge persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.knowledge import KnowledgeDocumentKind


class KnowledgePersistenceError(PersistenceError):
    """Base class for safe knowledge persistence failures."""


class KnowledgeDocumentNotFoundError(KnowledgePersistenceError):
    """Raised when a knowledge document does not exist."""


class KnowledgeDocumentVersionNotFoundError(KnowledgePersistenceError):
    """Raised when a knowledge document version does not exist."""


class DuplicateKnowledgeDocumentError(KnowledgePersistenceError):
    """Raised when a document uniqueness constraint is violated."""


class DuplicateKnowledgeDocumentVersionError(KnowledgePersistenceError):
    """Raised when a document version uniqueness constraint is violated."""


class DuplicateKnowledgeChunkError(KnowledgePersistenceError):
    """Raised when a chunk uniqueness constraint is violated."""


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentRecord:
    id: UUID
    tenant_id: UUID
    source_type: str
    external_reference: str | None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentVersionRecord:
    id: UUID
    tenant_id: UUID
    document_id: UUID
    version_number: int
    status: str
    content_id: UUID
    content_sha256_digest: bytes
    effective_from: datetime
    effective_to: datetime | None
    created_at: datetime
    approved_at: datetime | None
    indexed_at: datetime | None
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class KnowledgeChunkRecord:
    id: UUID
    tenant_id: UUID
    document_version_id: UUID
    content_id: UUID
    position: int
    status: str
    chunk_sha256_digest: bytes
    token_count: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeChunkTermRecord:
    chunk_id: UUID
    tenant_id: UUID
    term_digest: bytes
    weight_basis_points: int


@dataclass(frozen=True, slots=True)
class KnowledgeLexicalMatch:
    chunk_id: UUID
    content_id: UUID
    document_id: UUID
    document_version_id: UUID
    source_code: str
    version_number: int
    document_kind: KnowledgeDocumentKind
    match_weight: int
    matched_term_count: int
    chunk_position: int


class KnowledgeDocumentRepository(Protocol):
    async def add(self, record: KnowledgeDocumentRecord) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> KnowledgeDocumentRecord | None: ...

    async def list_by_tenant(
        self,
        *,
        tenant_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[KnowledgeDocumentRecord, ...]: ...


class KnowledgeDocumentVersionRepository(Protocol):
    async def add(self, record: KnowledgeDocumentVersionRecord) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
    ) -> KnowledgeDocumentVersionRecord | None: ...

    async def get_by_id_for_update(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
    ) -> KnowledgeDocumentVersionRecord | None: ...

    async def list_by_document(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        limit: int = 50,
    ) -> tuple[KnowledgeDocumentVersionRecord, ...]: ...

    async def allocate_next_version_number(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> int: ...

    async def mark_approved(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
        approved_at: datetime,
    ) -> KnowledgeDocumentVersionRecord: ...

    async def mark_indexed(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
        indexed_at: datetime,
    ) -> KnowledgeDocumentVersionRecord: ...

    async def mark_revoked(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
        revoked_at: datetime,
    ) -> KnowledgeDocumentVersionRecord: ...


class KnowledgeChunkRepository(Protocol):
    async def add_many(
        self,
        *,
        chunks: tuple[KnowledgeChunkRecord, ...],
    ) -> None: ...

    async def list_by_document_version(
        self,
        *,
        tenant_id: UUID,
        document_version_id: UUID,
    ) -> tuple[KnowledgeChunkRecord, ...]: ...

    async def revoke_by_document_version(
        self,
        *,
        tenant_id: UUID,
        document_version_id: UUID,
    ) -> int: ...


class KnowledgeChunkTermRepository(Protocol):
    async def replace_for_chunk(
        self,
        *,
        tenant_id: UUID,
        chunk_id: UUID,
        terms: tuple[KnowledgeChunkTermRecord, ...],
    ) -> None: ...

    async def search_ranked(
        self,
        *,
        tenant_id: UUID,
        term_digests: tuple[bytes, ...],
        limit: int,
    ) -> tuple[KnowledgeLexicalMatch, ...]: ...


class KnowledgeUnitOfWork(Protocol):
    knowledge_documents: KnowledgeDocumentRepository
    knowledge_document_versions: KnowledgeDocumentVersionRepository
    knowledge_chunks: KnowledgeChunkRepository
    knowledge_chunk_terms: KnowledgeChunkTermRepository

    async def __aenter__(self) -> KnowledgeUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
