"""Manager scorecard query service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.manager_attribution import thread_ids_for_manager
from closeros.application.metrics_query_service import MetricsQueryService
from closeros.application.product_audit import scorecard_viewed_event
from closeros.domain.audit import AuditActorType
from closeros.domain.identity import Role
from closeros.domain.metrics import METRIC_FORMULA_VERSION, MetricKey, MetricScope
from closeros.domain.product_metrics import (
    SCORECARD_FORMULA_VERSION,
    ScorecardComponents,
    delta_basis_points,
    finding_discipline_basis_points,
    task_completion_basis_points,
)
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
from closeros.infrastructure.product_query_repositories import ProductQueryRepository

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]

_PRIVILEGED_SCORECARD_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN})


@dataclass(frozen=True, slots=True)
class FindingCountSummary:
    finding_code: str
    severity: str
    count: int


@dataclass(frozen=True, slots=True)
class ManagerScorecard:
    membership_id: UUID
    manager_user_id: UUID
    formula_version: str
    window_start: datetime
    window_end: datetime
    components: ScorecardComponents
    composite_basis_points: int
    composite_delta_basis_points: int
    finding_counts: tuple[FindingCountSummary, ...]
    task_counts: dict[str, int]


class ScorecardAccessDeniedError(PermissionError):
    """Raised when scorecard access is denied."""


class ScorecardQueryService:
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

    async def list_manager_scorecards(
        self,
        *,
        tenant_id: UUID,
        roles: frozenset[Role],
        actor_user_id: UUID,
        window_start: datetime,
        window_end: datetime,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> tuple[ManagerScorecard, ...]:
        if Role.ANALYST in roles and not roles.intersection(_PRIVILEGED_SCORECARD_ROLES):
            raise ScorecardAccessDeniedError("access denied")
        uow = self._uow_factory()
        async with uow:
            memberships = await uow.memberships.list_for_tenant(tenant_id)
        cards: list[ManagerScorecard] = []
        for membership in memberships:
            if not membership.roles.intersection({Role.MANAGER, Role.SALES_HEAD}):
                continue
            if (
                Role.MANAGER in membership.roles
                and not roles.intersection(_PRIVILEGED_SCORECARD_ROLES)
                and membership.user_id != actor_user_id
            ):
                continue
            card = await self._build_card(
                tenant_id=tenant_id,
                membership_id=membership.id,
                manager_user_id=membership.user_id,
                window_start=window_start,
                window_end=window_end,
            )
            cards.append(card)
        if cards:
            uow = self._uow_factory()
            async with uow:
                await append_required_audit_event(
                    uow.audit_events,
                    scorecard_viewed_event(
                        tenant_id=tenant_id,
                        membership_id=cards[0].membership_id,
                        occurred_at=self._clock(),
                        audit_context=audit_context,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        event_id=self._uuid_factory(),
                        score_formula_version=SCORECARD_FORMULA_VERSION,
                    ),
                )
                await uow.commit()
        return tuple(cards)

    async def get_scorecard(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        roles: frozenset[Role],
        actor_user_id: UUID,
        window_start: datetime,
        window_end: datetime,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> ManagerScorecard | None:
        if Role.ANALYST in roles and not roles.intersection(_PRIVILEGED_SCORECARD_ROLES):
            raise ScorecardAccessDeniedError("access denied")
        uow = self._uow_factory()
        async with uow:
            membership = await uow.memberships.get_by_id(
                tenant_id=tenant_id,
                membership_id=membership_id,
            )
            if membership is None:
                return None
            if (
                Role.MANAGER in membership.roles
                and not roles.intersection(_PRIVILEGED_SCORECARD_ROLES)
                and membership.user_id != actor_user_id
            ):
                raise ScorecardAccessDeniedError("access denied")
            card = await self._build_card(
                tenant_id=tenant_id,
                membership_id=membership.id,
                manager_user_id=membership.user_id,
                window_start=window_start,
                window_end=window_end,
            )
            await append_required_audit_event(
                uow.audit_events,
                scorecard_viewed_event(
                    tenant_id=tenant_id,
                    membership_id=membership_id,
                    occurred_at=self._clock(),
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                    score_formula_version=SCORECARD_FORMULA_VERSION,
                ),
            )
            await uow.commit()
        return card

    async def _build_card(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        manager_user_id: UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> ManagerScorecard:
        duration = window_end - window_start
        previous_end = window_start
        previous_start = previous_end - duration
        now = self._clock()
        current = await self._metrics_query_service.list_snapshots(
            tenant_id=tenant_id,
            scope=MetricScope.MANAGER,
            manager_user_id=manager_user_id,
            window_start=window_start,
            window_end=window_end,
            formula_version=METRIC_FORMULA_VERSION,
        )
        previous = await self._metrics_query_service.list_snapshots(
            tenant_id=tenant_id,
            scope=MetricScope.MANAGER,
            manager_user_id=manager_user_id,
            window_start=previous_start,
            window_end=previous_end,
            formula_version=METRIC_FORMULA_VERSION,
        )
        current_values = _values_by_key(current[0] if current else None)
        previous_values = _values_by_key(previous[0] if previous else None)
        high_critical_open = 0
        finding_counts: tuple[FindingCountSummary, ...] = ()
        task_counts_dict = {
            "open": 0,
            "in_progress": 0,
            "overdue": 0,
            "completed": 0,
            "cancelled": 0,
        }
        previous_high_critical_open = 0
        previous_task_completed = 0
        previous_task_overdue = 0
        uow = self._uow_factory()
        async with uow:
            if isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
                repo = ProductQueryRepository(uow.session)
                attribution = await repo.load_attribution(
                    tenant_id=tenant_id, window_end=window_end
                )
                manager_threads = thread_ids_for_manager(
                    attributed=attribution,
                    manager_user_id=manager_user_id,
                )
                high_critical_open = await repo.count_open_findings_for_threads(
                    tenant_id=tenant_id,
                    thread_ids=manager_threads,
                    severity="high_critical",
                )
                previous_attribution = await repo.load_attribution(
                    tenant_id=tenant_id,
                    window_end=previous_end,
                )
                previous_manager_threads = thread_ids_for_manager(
                    attributed=previous_attribution,
                    manager_user_id=manager_user_id,
                )
                previous_high_critical_open = await repo.count_open_findings_for_threads(
                    tenant_id=tenant_id,
                    thread_ids=previous_manager_threads,
                    severity="high_critical",
                )
                by_code = await repo.finding_counts_by_code_for_manager_threads(
                    tenant_id=tenant_id,
                    thread_ids=manager_threads,
                )
                finding_counts = tuple(
                    FindingCountSummary(
                        finding_code=item.finding_code,
                        severity=item.severity,
                        count=item.count,
                    )
                    for item in by_code
                )
                task_stats = await repo.task_counts_for_membership(
                    tenant_id=tenant_id,
                    membership_id=membership_id,
                    now=now,
                )
                previous_task_stats = await repo.task_counts_for_membership(
                    tenant_id=tenant_id,
                    membership_id=membership_id,
                    now=previous_end,
                )
                task_counts_dict = {
                    "open": task_stats.open_count,
                    "in_progress": task_stats.in_progress_count,
                    "overdue": task_stats.overdue_count,
                    "completed": task_stats.completed_count,
                    "cancelled": task_stats.cancelled_count,
                }
                previous_task_completed = previous_task_stats.completed_count
                previous_task_overdue = previous_task_stats.overdue_count
        components = ScorecardComponents(
            response_rate_basis_points=current_values.get(MetricKey.RESPONSE_RATE_BASIS_POINTS, 0),
            conversion_rate_basis_points=current_values.get(
                MetricKey.CONVERSION_RATE_BASIS_POINTS, 0
            ),
            finding_discipline_basis_points=finding_discipline_basis_points(
                high_critical_open_findings=high_critical_open,
                active_thread_count=current_values.get(MetricKey.ACTIVE_THREAD_COUNT, 0),
            ),
            task_completion_basis_points=task_completion_basis_points(
                completed_count=task_counts_dict["completed"],
                overdue_count=task_counts_dict["overdue"],
            ),
        )
        previous_components = ScorecardComponents(
            response_rate_basis_points=previous_values.get(MetricKey.RESPONSE_RATE_BASIS_POINTS, 0),
            conversion_rate_basis_points=previous_values.get(
                MetricKey.CONVERSION_RATE_BASIS_POINTS, 0
            ),
            finding_discipline_basis_points=finding_discipline_basis_points(
                high_critical_open_findings=previous_high_critical_open,
                active_thread_count=previous_values.get(MetricKey.ACTIVE_THREAD_COUNT, 0),
            ),
            task_completion_basis_points=task_completion_basis_points(
                completed_count=previous_task_completed,
                overdue_count=previous_task_overdue,
            ),
        )
        return ManagerScorecard(
            membership_id=membership_id,
            manager_user_id=manager_user_id,
            formula_version=SCORECARD_FORMULA_VERSION,
            window_start=window_start,
            window_end=window_end,
            components=components,
            composite_basis_points=components.composite_basis_points(),
            composite_delta_basis_points=delta_basis_points(
                current=components.composite_basis_points(),
                previous=previous_components.composite_basis_points(),
            ),
            finding_counts=finding_counts,
            task_counts=task_counts_dict,
        )


def _values_by_key(snapshot: object | None) -> dict[MetricKey, int]:
    if snapshot is None:
        return {}
    return {value.key: value.value for value in snapshot.values}  # type: ignore[attr-defined]
