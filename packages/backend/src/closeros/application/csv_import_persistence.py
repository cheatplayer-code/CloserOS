"""Application-layer persistence ports for controlled CSV import batches."""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.csv_import import CsvImportBatch, CsvImportRowError


class CsvImportPersistenceError(PersistenceError):
    """Base class for safe CSV import persistence failures."""


class CsvImportRecordNotFoundError(CsvImportPersistenceError):
    """Raised when a CSV import batch does not exist."""


class DuplicateCsvImportBatchError(CsvImportPersistenceError):
    """Raised when an idempotency key already exists."""


class CsvImportStaleVersionError(CsvImportPersistenceError):
    """Raised when optimistic concurrency rejects an update."""


@dataclass(frozen=True, slots=True)
class CsvImportRowErrorQuery:
    limit: int = 100
    offset: int = 0


class CsvImportBatchRepository(Protocol):
    async def add(self, batch: CsvImportBatch) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        import_id: UUID,
    ) -> CsvImportBatch | None: ...

    async def get_for_update(
        self,
        *,
        tenant_id: UUID,
        import_id: UUID,
    ) -> CsvImportBatch | None: ...

    async def get_by_idempotency_key(
        self,
        *,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> CsvImportBatch | None: ...

    async def update(self, batch: CsvImportBatch) -> None: ...


class CsvImportRowErrorRepository(Protocol):
    async def append(self, error: CsvImportRowError) -> None: ...

    async def list_by_import(
        self,
        *,
        tenant_id: UUID,
        import_id: UUID,
        query: CsvImportRowErrorQuery,
    ) -> tuple[CsvImportRowError, ...]: ...


class CsvImportUnitOfWork(Protocol):
    csv_import_batches: CsvImportBatchRepository
    csv_import_row_errors: CsvImportRowErrorRepository

    async def __aenter__(self) -> CsvImportUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
