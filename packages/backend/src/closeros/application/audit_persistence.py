"""Application-layer persistence ports for the audit subsystem."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from closeros.domain.audit import AuditAction, AuditEvent, AuditTargetType


class AuditPersistenceError(Exception):
    """Base class for safe audit persistence failures."""


class AuditAppendRequiredError(AuditPersistenceError):
    """Raised when a required audit append fails."""


@dataclass(frozen=True, slots=True)
class AuditQueryFilter:
    tenant_id: UUID
    action: AuditAction | None = None
    actor_id: UUID | None = None
    target_type: AuditTargetType | None = None
    target_id: UUID | None = None
    correlation_id: UUID | None = None
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None


@dataclass(frozen=True, slots=True)
class AuditQueryCursor:
    occurred_at: datetime
    event_id: UUID


@dataclass(frozen=True, slots=True)
class AuditQueryPage:
    events: tuple[AuditEvent, ...]
    next_cursor: AuditQueryCursor | None


class AuditEventAppendRepository(Protocol):
    async def append(self, event: AuditEvent) -> None: ...


class AuditEventRepository(AuditEventAppendRepository, Protocol):

    async def query_page(
        self,
        *,
        query_filter: AuditQueryFilter,
        cursor: AuditQueryCursor | None,
        page_size: int,
    ) -> AuditQueryPage: ...


class AuditUnitOfWork(Protocol):
    audit_events: AuditEventRepository

    async def __aenter__(self) -> AuditUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
