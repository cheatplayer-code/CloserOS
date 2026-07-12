"""Application persistence ports for follow-up tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.follow_up_task import FollowUpTaskPriority, FollowUpTaskStatus
from closeros.infrastructure.cursor_pagination import KeysetCursor, KeysetPage


class FollowUpTaskPersistenceError(PersistenceError):
    """Base class for follow-up task persistence failures."""


class FollowUpTaskNotFoundError(FollowUpTaskPersistenceError):
    """Raised when a follow-up task cannot be found."""


class FollowUpTaskVersionConflictError(FollowUpTaskPersistenceError):
    """Raised when optimistic concurrency detects a stale version."""


@dataclass(frozen=True, slots=True)
class FollowUpTaskRecord:
    id: UUID
    tenant_id: UUID
    conversation_thread_id: UUID
    source_finding_id: UUID | None
    title: str
    status: FollowUpTaskStatus
    priority: FollowUpTaskPriority
    assigned_membership_id: UUID | None
    created_by_user_id: UUID
    due_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class FollowUpTaskListFilter:
    tenant_id: UUID
    status: FollowUpTaskStatus | None = None
    assigned_membership_id: UUID | None = None
    conversation_thread_id: UUID | None = None
    due_before: datetime | None = None
    due_after: datetime | None = None
    overdue_only: bool = False
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class FollowUpTaskCounts:
    open_count: int
    in_progress_count: int
    overdue_count: int
    completed_count: int
    cancelled_count: int


class FollowUpTaskRepository(Protocol):
    async def add(self, *, record: FollowUpTaskRecord) -> None: ...

    async def get_by_id(self, *, tenant_id: UUID, task_id: UUID) -> FollowUpTaskRecord | None: ...

    async def get_by_id_for_update(
        self,
        *,
        tenant_id: UUID,
        task_id: UUID,
    ) -> FollowUpTaskRecord | None: ...

    async def update(
        self, *, record: FollowUpTaskRecord, expected_version: int
    ) -> FollowUpTaskRecord: ...

    async def list_page(
        self,
        *,
        filters: FollowUpTaskListFilter,
        limit: int,
        cursor: KeysetCursor | None,
    ) -> KeysetPage[FollowUpTaskRecord]: ...

    async def count_by_status(
        self,
        *,
        tenant_id: UUID,
        now: datetime,
    ) -> FollowUpTaskCounts: ...

    async def has_unresolved_for_thread(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID,
    ) -> bool: ...
