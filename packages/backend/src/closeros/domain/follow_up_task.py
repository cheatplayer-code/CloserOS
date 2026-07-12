"""Framework-independent follow-up task domain model and state machine."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_TITLE_PATTERN = re.compile(r"^[\w\s.,!?;:()\-'\"]{1,200}$", re.UNICODE)
_MAX_TITLE_LENGTH = 200


class FollowUpTaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class FollowUpTaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


_ALLOWED_TRANSITIONS: dict[FollowUpTaskStatus, frozenset[FollowUpTaskStatus]] = {
    FollowUpTaskStatus.OPEN: frozenset(
        {FollowUpTaskStatus.IN_PROGRESS, FollowUpTaskStatus.COMPLETED, FollowUpTaskStatus.CANCELLED}
    ),
    FollowUpTaskStatus.IN_PROGRESS: frozenset(
        {FollowUpTaskStatus.COMPLETED, FollowUpTaskStatus.CANCELLED, FollowUpTaskStatus.OPEN}
    ),
    FollowUpTaskStatus.COMPLETED: frozenset({FollowUpTaskStatus.OPEN}),
    FollowUpTaskStatus.CANCELLED: frozenset({FollowUpTaskStatus.OPEN}),
}


class FollowUpTaskTransitionError(ValueError):
    """Raised when a follow-up task state transition is not allowed."""


def _validate_uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")
    return value


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _validate_title(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("title must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("title must not be empty")
    if len(normalized) > _MAX_TITLE_LENGTH:
        raise ValueError("title exceeds maximum length")
    if not _TITLE_PATTERN.fullmatch(normalized):
        raise ValueError("title contains unsupported characters")
    return normalized


def validate_follow_up_task_transition(
    *,
    current: FollowUpTaskStatus,
    target: FollowUpTaskStatus,
) -> None:
    if current is target:
        return
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise FollowUpTaskTransitionError("follow-up task transition is not allowed")


def reopen_is_allowed(*, current: FollowUpTaskStatus) -> bool:
    return FollowUpTaskStatus.OPEN in _ALLOWED_TRANSITIONS.get(current, frozenset())


@dataclass(frozen=True, slots=True)
class FollowUpTask:
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

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.conversation_thread_id, "conversation_thread_id")
        if self.source_finding_id is not None:
            _validate_uuid(self.source_finding_id, "source_finding_id")
        object.__setattr__(self, "title", _validate_title(self.title))
        if not isinstance(self.status, FollowUpTaskStatus):
            raise TypeError("status must be a FollowUpTaskStatus")
        if not isinstance(self.priority, FollowUpTaskPriority):
            raise TypeError("priority must be a FollowUpTaskPriority")
        if self.assigned_membership_id is not None:
            _validate_uuid(self.assigned_membership_id, "assigned_membership_id")
        _validate_uuid(self.created_by_user_id, "created_by_user_id")
        if self.due_at is not None:
            object.__setattr__(
                self, "due_at", _validate_timezone_aware_datetime(self.due_at, "due_at")
            )
        if self.completed_at is not None:
            object.__setattr__(
                self,
                "completed_at",
                _validate_timezone_aware_datetime(self.completed_at, "completed_at"),
            )
        if self.cancelled_at is not None:
            object.__setattr__(
                self,
                "cancelled_at",
                _validate_timezone_aware_datetime(self.cancelled_at, "cancelled_at"),
            )
        object.__setattr__(
            self,
            "created_at",
            _validate_timezone_aware_datetime(self.created_at, "created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _validate_timezone_aware_datetime(self.updated_at, "updated_at"),
        )
        if not isinstance(self.version, int) or isinstance(self.version, bool):
            raise TypeError("version must be an int")
        if self.version < 1:
            raise ValueError("version must be positive")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        if self.status is FollowUpTaskStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed tasks require completed_at")
        if self.status is FollowUpTaskStatus.CANCELLED and self.cancelled_at is None:
            raise ValueError("cancelled tasks require cancelled_at")
