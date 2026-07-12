"""Audit recording helpers for mandatory and standalone append paths."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol
from uuid import UUID

from closeros.application.audit_persistence import (
    AuditAppendRequiredError,
    AuditEventAppendRepository,
)
from closeros.domain.audit import AuditEvent


class StandaloneAuditUnitOfWork(Protocol):
    audit_events: AuditEventAppendRepository

    async def __aenter__(self) -> StandaloneAuditUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


_UnitOfWorkFactory = Callable[[], StandaloneAuditUnitOfWork]


@dataclass(frozen=True, slots=True)
class AuditContext:
    correlation_id: UUID
    http_method: str | None = None
    route_template: str | None = None


async def append_required_audit_event(
    repository: AuditEventAppendRepository,
    event: AuditEvent,
) -> None:
    try:
        await repository.append(event)
    except Exception as error:
        raise AuditAppendRequiredError("required audit append failed") from error


class StandaloneAuditAppender:
    """Append audit events in a dedicated transaction."""

    def __init__(self, uow_factory: _UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def append(self, event: AuditEvent) -> None:
        uow = self._uow_factory()
        async with uow:
            await append_required_audit_event(uow.audit_events, event)
            await uow.commit()


class AuditAppendHook(Protocol):
    def __call__(self, event: AuditEvent) -> Awaitable[None]: ...
