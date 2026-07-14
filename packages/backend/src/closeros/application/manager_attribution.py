"""Canonical manager attribution shared by metrics and RSTU product queries.

V1 rule — attribute a thread or sales case to the latest eligible assignment
effective at the requested cutoff (``assigned_at <= window_end``):

1. Thread-level assignment wins over SalesCase-level assignment for a thread.
2. Among assignments of the same kind, pick the latest ``assigned_at``.
3. Tie-break: ``assignment_id`` UUID lexicographic order (higher wins).
4. Direct sales-case assignments without a thread contribute to manager
   ``sales_case_ids`` (CRM / appointment metrics).
5. Unassigned threads/cases are excluded from manager scope.

Never infer manager identity from message content or provider metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.application.metrics_source_data import (
    MetricsAssignmentRow,
    MetricsSourceData,
    MetricsThreadRow,
)


@dataclass(frozen=True, slots=True)
class ManagerMetricScope:
    """Thread and sales-case IDs attributed to one manager at a cutoff."""

    thread_ids: frozenset[UUID]
    sales_case_ids: frozenset[UUID]


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


def resolve_manager_metric_scope(
    *,
    source_data: MetricsSourceData,
    manager_user_id: UUID,
    window_end: datetime,
) -> ManagerMetricScope:
    """Single attribution entry point for all manager-scoped metrics."""
    attributed = attribute_threads_to_managers(
        threads=source_data.threads,
        assignments=source_data.assignments,
        window_end=window_end,
    )
    thread_ids = thread_ids_for_manager(
        attributed=attributed,
        manager_user_id=manager_user_id,
    )
    sales_case_ids: set[UUID] = set()
    winning_case_assignments: dict[UUID, MetricsAssignmentRow] = {}
    for assignment in source_data.assignments:
        if assignment.assigned_at > window_end:
            continue
        if assignment.sales_case_id is None:
            continue
        current = winning_case_assignments.get(assignment.sales_case_id)
        if current is None or assignment_precedence(assignment, current):
            winning_case_assignments[assignment.sales_case_id] = assignment
    for sales_case_id, assignment in winning_case_assignments.items():
        if assignment.manager_user_id == manager_user_id:
            sales_case_ids.add(sales_case_id)

    threads_by_id = {thread.id: thread for thread in source_data.threads}
    for thread_id in thread_ids:
        thread = threads_by_id.get(thread_id)
        if thread is not None and thread.sales_case_id is not None:
            sales_case_ids.add(thread.sales_case_id)

    return ManagerMetricScope(
        thread_ids=thread_ids,
        sales_case_ids=frozenset(sales_case_ids),
    )


__all__ = [
    "ManagerMetricScope",
    "assignment_precedence",
    "attribute_threads_to_managers",
    "resolve_manager_metric_scope",
    "thread_ids_for_manager",
]
