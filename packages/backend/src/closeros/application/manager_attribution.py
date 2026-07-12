"""Canonical manager attribution shared by metrics and RSTU product queries.

Precedence (matches ``lm-metrics-v1`` / ``MetricsEngine``):

1. Thread-level assignment wins over SalesCase-level assignment.
2. Among assignments of the same kind, pick the latest ``assigned_at`` not after
   ``window_end``.
3. Tie-break: ``assignment_id DESC`` (UUID lexical order).

Never infer manager identity from message content or provider metadata.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from closeros.application.metrics_source_data import MetricsAssignmentRow, MetricsThreadRow


def assignment_precedence(
    candidate: MetricsAssignmentRow,
    current: MetricsAssignmentRow,
) -> bool:
    if candidate.assigned_at != current.assigned_at:
        return candidate.assigned_at > current.assigned_at
    return str(candidate.id) > str(current.id)


def attribute_threads_to_managers(
    *,
    threads: tuple[MetricsThreadRow, ...],
    assignments: tuple[MetricsAssignmentRow, ...],
    window_end: datetime,
) -> dict[UUID, UUID]:
    threads_by_id = {thread.id: thread for thread in threads}
    winning_assignment_by_thread: dict[UUID, MetricsAssignmentRow] = {}
    winning_assignment_by_sales_case: dict[UUID, MetricsAssignmentRow] = {}

    for assignment in assignments:
        if assignment.assigned_at > window_end:
            continue
        if assignment.conversation_thread_id is not None:
            current = winning_assignment_by_thread.get(assignment.conversation_thread_id)
            if current is None or assignment_precedence(assignment, current):
                winning_assignment_by_thread[assignment.conversation_thread_id] = assignment
        if assignment.sales_case_id is not None:
            current = winning_assignment_by_sales_case.get(assignment.sales_case_id)
            if current is None or assignment_precedence(assignment, current):
                winning_assignment_by_sales_case[assignment.sales_case_id] = assignment

    attributed: dict[UUID, UUID] = {}
    for thread_id, thread in threads_by_id.items():
        thread_assignment = winning_assignment_by_thread.get(thread_id)
        if thread_assignment is not None:
            attributed[thread_id] = thread_assignment.manager_user_id
            continue
        if thread.sales_case_id is not None:
            case_assignment = winning_assignment_by_sales_case.get(thread.sales_case_id)
            if case_assignment is not None:
                attributed[thread_id] = case_assignment.manager_user_id
    return attributed


def thread_ids_for_manager(
    *,
    attributed: dict[UUID, UUID],
    manager_user_id: UUID,
) -> frozenset[UUID]:
    return frozenset(
        thread_id
        for thread_id, attributed_manager in attributed.items()
        if attributed_manager == manager_user_id
    )
