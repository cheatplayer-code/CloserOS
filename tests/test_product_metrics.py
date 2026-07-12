"""Unit tests for RSTU dashboard and scorecard formulas."""

from __future__ import annotations

from closeros.domain.product_metrics import (
    ScorecardComponents,
    delta_basis_points,
    finding_discipline_basis_points,
    task_completion_basis_points,
)


def test_finding_discipline_penalizes_open_high_critical_findings() -> None:
    perfect = finding_discipline_basis_points(
        high_critical_open_findings=0,
        active_thread_count=10,
    )
    penalized = finding_discipline_basis_points(
        high_critical_open_findings=5,
        active_thread_count=10,
    )
    assert perfect == 10_000
    assert penalized < perfect


def test_task_completion_basis_points() -> None:
    assert task_completion_basis_points(completed_count=3, overdue_count=1) == 7500
    assert task_completion_basis_points(completed_count=0, overdue_count=0) == 10_000


def test_scorecard_composite_weighting() -> None:
    components = ScorecardComponents(
        response_rate_basis_points=10_000,
        conversion_rate_basis_points=10_000,
        finding_discipline_basis_points=10_000,
        task_completion_basis_points=10_000,
    )
    assert components.composite_basis_points() == 10_000
    assert delta_basis_points(current=9000, previous=8000) == 1000
