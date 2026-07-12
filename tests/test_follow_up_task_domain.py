"""Domain tests for follow-up task state machine and invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from closeros.domain.follow_up_task import (
    FollowUpTask,
    FollowUpTaskPriority,
    FollowUpTaskStatus,
    FollowUpTaskTransitionError,
    validate_follow_up_task_transition,
)

_TASK_ID = UUID("00000000-0000-0000-0000-000000000701")
_TENANT_ID = UUID("00000000-0000-0000-0000-000000000300")
_THREAD_ID = UUID("00000000-0000-0000-0000-000000000601")
_USER_ID = UUID("00000000-0000-0000-0000-000000000010")
_NOW = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)


def _task(
    *,
    status: FollowUpTaskStatus = FollowUpTaskStatus.OPEN,
    completed_at: datetime | None = None,
    cancelled_at: datetime | None = None,
) -> FollowUpTask:
    if status is FollowUpTaskStatus.COMPLETED and completed_at is None:
        completed_at = _NOW
    if status is FollowUpTaskStatus.CANCELLED and cancelled_at is None:
        cancelled_at = _NOW
    return FollowUpTask(
        id=_TASK_ID,
        tenant_id=_TENANT_ID,
        conversation_thread_id=_THREAD_ID,
        source_finding_id=None,
        title="Follow up on pricing",
        status=status,
        priority=FollowUpTaskPriority.NORMAL,
        assigned_membership_id=None,
        created_by_user_id=_USER_ID,
        due_at=None,
        completed_at=completed_at,
        cancelled_at=cancelled_at,
        created_at=_NOW,
        updated_at=_NOW,
        version=1,
    )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (FollowUpTaskStatus.OPEN, FollowUpTaskStatus.IN_PROGRESS),
        (FollowUpTaskStatus.IN_PROGRESS, FollowUpTaskStatus.COMPLETED),
        (FollowUpTaskStatus.COMPLETED, FollowUpTaskStatus.OPEN),
        (FollowUpTaskStatus.CANCELLED, FollowUpTaskStatus.OPEN),
    ],
)
def test_allowed_transitions(current: FollowUpTaskStatus, target: FollowUpTaskStatus) -> None:
    validate_follow_up_task_transition(current=current, target=target)


def test_disallowed_transition_raises() -> None:
    with pytest.raises(FollowUpTaskTransitionError):
        validate_follow_up_task_transition(
            current=FollowUpTaskStatus.COMPLETED,
            target=FollowUpTaskStatus.CANCELLED,
        )


def test_completed_task_requires_completed_at() -> None:
    with pytest.raises(ValueError, match="completed_at"):
        FollowUpTask(
            id=_TASK_ID,
            tenant_id=_TENANT_ID,
            conversation_thread_id=_THREAD_ID,
            source_finding_id=None,
            title="Follow up on pricing",
            status=FollowUpTaskStatus.COMPLETED,
            priority=FollowUpTaskPriority.NORMAL,
            assigned_membership_id=None,
            created_by_user_id=_USER_ID,
            due_at=None,
            completed_at=None,
            cancelled_at=None,
            created_at=_NOW,
            updated_at=_NOW,
            version=1,
        )


def test_title_validation_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        FollowUpTask(
            id=_TASK_ID,
            tenant_id=_TENANT_ID,
            conversation_thread_id=_THREAD_ID,
            source_finding_id=None,
            title="   ",
            status=FollowUpTaskStatus.OPEN,
            priority=FollowUpTaskPriority.NORMAL,
            assigned_membership_id=None,
            created_by_user_id=_USER_ID,
            due_at=None,
            completed_at=None,
            cancelled_at=None,
            created_at=_NOW,
            updated_at=_NOW,
            version=1,
        )
