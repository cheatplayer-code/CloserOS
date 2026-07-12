"""Versioned integer formulas for RSTU dashboard and scorecards."""

from __future__ import annotations

from dataclasses import dataclass

DASHBOARD_FORMULA_VERSION = "rstu-dashboard-v1"
SCORECARD_FORMULA_VERSION = "rstu-scorecard-v1"

_WEIGHT_RESPONSE_RATE_BPS = 4000
_WEIGHT_CONVERSION_RATE_BPS = 3000
_WEIGHT_FINDING_DISCIPLINE_BPS = 2000
_WEIGHT_TASK_COMPLETION_BPS = 1000
_BASIS_POINT_SCALE = 10_000


@dataclass(frozen=True, slots=True)
class ScorecardComponents:
    response_rate_basis_points: int
    conversion_rate_basis_points: int
    finding_discipline_basis_points: int
    task_completion_basis_points: int

    def composite_basis_points(self) -> int:
        weighted = (
            self.response_rate_basis_points * _WEIGHT_RESPONSE_RATE_BPS
            + self.conversion_rate_basis_points * _WEIGHT_CONVERSION_RATE_BPS
            + self.finding_discipline_basis_points * _WEIGHT_FINDING_DISCIPLINE_BPS
            + self.task_completion_basis_points * _WEIGHT_TASK_COMPLETION_BPS
        )
        return weighted // _BASIS_POINT_SCALE


def finding_discipline_basis_points(
    *,
    high_critical_open_findings: int,
    active_thread_count: int,
) -> int:
    if active_thread_count <= 0:
        return _BASIS_POINT_SCALE if high_critical_open_findings == 0 else 0
    penalty_per_thread = min(
        _BASIS_POINT_SCALE,
        (high_critical_open_findings * _BASIS_POINT_SCALE) // active_thread_count,
    )
    return max(0, _BASIS_POINT_SCALE - penalty_per_thread)


def task_completion_basis_points(*, completed_count: int, overdue_count: int) -> int:
    denominator = completed_count + overdue_count
    if denominator <= 0:
        return _BASIS_POINT_SCALE
    return min(_BASIS_POINT_SCALE, (completed_count * _BASIS_POINT_SCALE) // denominator)


def delta_basis_points(*, current: int, previous: int) -> int:
    return current - previous
