"""Owner dashboard aggregation service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.metrics_query_service import MetricsQueryService
from closeros.application.product_audit import dashboard_viewed_event
from closeros.domain.audit import AuditActorType
from closeros.domain.metrics import METRIC_FORMULA_VERSION, MetricKey, MetricScope
from closeros.domain.product_metrics import DASHBOARD_FORMULA_VERSION, delta_basis_points
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
from closeros.infrastructure.product_query_repositories import ProductQueryRepository

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class DashboardMetricValue:
    key: str
    current_value: int
    previous_value: int
    delta: int


@dataclass(frozen=True, slots=True)
class ManagerPerformanceSummary:
    manager_user_id: UUID
    response_rate_basis_points: int
    conversion_rate_basis_points: int
    active_thread_count: int


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    formula_version: str
    window_start: datetime
    window_end: datetime
    previous_window_start: datetime
    previous_window_end: datetime
    total_conversations: int
    open_high_severity_findings: int
    overdue_follow_up_tasks: int
    metrics: tuple[DashboardMetricValue, ...]
    manager_summaries: tuple[ManagerPerformanceSummary, ...]


class DashboardQueryService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        metrics_query_service: MetricsQueryService,
        uuid_factory: _UuidFactory,
        clock: _Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._metrics_query_service = metrics_query_service
        self._uuid_factory = uuid_factory
        self._clock = clock

    async def get_dashboard(
        self,
        *,
        tenant_id: UUID,
        window_start: datetime,
        window_end: datetime,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> DashboardSummary:
        duration = window_end - window_start
        previous_end = window_start
        previous_start = previous_end - duration
        current_snapshots = await self._metrics_query_service.list_snapshots(
            tenant_id=tenant_id,
            scope=MetricScope.TENANT,
            manager_user_id=None,
            window_start=window_start,
            window_end=window_end,
            formula_version=METRIC_FORMULA_VERSION,
        )
        previous_snapshots = await self._metrics_query_service.list_snapshots(
            tenant_id=tenant_id,
            scope=MetricScope.TENANT,
            manager_user_id=None,
            window_start=previous_start,
            window_end=previous_end,
            formula_version=METRIC_FORMULA_VERSION,
        )
        current_values = _values_by_key(current_snapshots[0] if current_snapshots else None)
        previous_values = _values_by_key(previous_snapshots[0] if previous_snapshots else None)
        metric_rows: list[DashboardMetricValue] = []
        for key in (
            MetricKey.ACTIVE_THREAD_COUNT,
            MetricKey.RESPONSE_RATE_BASIS_POINTS,
            MetricKey.MEDIAN_FIRST_RESPONSE_SECONDS,
            MetricKey.P90_FIRST_RESPONSE_SECONDS,
            MetricKey.CONVERSION_RATE_BASIS_POINTS,
        ):
            current = current_values.get(key, 0)
            previous = previous_values.get(key, 0)
            if key in {
                MetricKey.RESPONSE_RATE_BASIS_POINTS,
                MetricKey.CONVERSION_RATE_BASIS_POINTS,
            }:
                delta = delta_basis_points(current=current, previous=previous)
            else:
                delta = current - previous
            metric_rows.append(
                DashboardMetricValue(
                    key=key.value,
                    current_value=current,
                    previous_value=previous,
                    delta=delta,
                )
            )
        now = self._clock()
        uow = self._uow_factory()
        async with uow:
            task_counts = await uow.follow_up_tasks.count_by_status(tenant_id=tenant_id, now=now)
            open_high_findings = 0
            manager_summaries: tuple[ManagerPerformanceSummary, ...] = ()
            if isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
                repo = ProductQueryRepository(uow.session)
                attribution = await repo.load_attribution(
                    tenant_id=tenant_id, window_end=window_end
                )
                all_thread_ids = frozenset(attribution.keys())
                open_high_findings = await repo.count_open_findings_for_threads(
                    tenant_id=tenant_id,
                    thread_ids=all_thread_ids,
                    severity="high_critical",
                )
                summaries: list[ManagerPerformanceSummary] = []
                manager_ids = frozenset(attribution.values())
                for manager_user_id in sorted(manager_ids, key=str):
                    snapshots = await self._metrics_query_service.list_snapshots(
                        tenant_id=tenant_id,
                        scope=MetricScope.MANAGER,
                        manager_user_id=manager_user_id,
                        window_start=window_start,
                        window_end=window_end,
                        formula_version=METRIC_FORMULA_VERSION,
                    )
                    values = _values_by_key(snapshots[0] if snapshots else None)
                    summaries.append(
                        ManagerPerformanceSummary(
                            manager_user_id=manager_user_id,
                            response_rate_basis_points=values.get(
                                MetricKey.RESPONSE_RATE_BASIS_POINTS, 0
                            ),
                            conversion_rate_basis_points=values.get(
                                MetricKey.CONVERSION_RATE_BASIS_POINTS, 0
                            ),
                            active_thread_count=values.get(MetricKey.ACTIVE_THREAD_COUNT, 0),
                        )
                    )
                manager_summaries = tuple(summaries)
            await append_required_audit_event(
                uow.audit_events,
                dashboard_viewed_event(
                    tenant_id=tenant_id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                    window_code=f"custom_{window_start.date().isoformat()}",
                ),
            )
            await uow.commit()
        return DashboardSummary(
            formula_version=DASHBOARD_FORMULA_VERSION,
            window_start=window_start,
            window_end=window_end,
            previous_window_start=previous_start,
            previous_window_end=previous_end,
            total_conversations=current_values.get(MetricKey.ACTIVE_THREAD_COUNT, 0),
            open_high_severity_findings=open_high_findings,
            overdue_follow_up_tasks=task_counts.overdue_count,
            metrics=tuple(metric_rows),
            manager_summaries=manager_summaries,
        )


def _values_by_key(snapshot: object | None) -> dict[MetricKey, int]:
    if snapshot is None:
        return {}
    return {value.key: value.value for value in snapshot.values}  # type: ignore[attr-defined]
