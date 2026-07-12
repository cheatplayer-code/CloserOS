"""Outbox handler for tenant metrics recalculation jobs."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.metrics_audit import metrics_snapshot_completed_event
from closeros.application.metrics_engine import MetricsEngine
from closeros.application.metrics_persistence import DuplicateMetricSnapshotError
from closeros.application.metrics_windows import (
    daily_window_for_local_date,
    local_date_from_timestamp,
    rolling_30_day_window_for_local_date,
)
from closeros.domain.audit import AuditActorType
from closeros.domain.metrics import METRIC_FORMULA_VERSION, MetricScope, MetricWindow
from closeros.domain.outbox import OutboxErrorCode, OutboxJob
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
from closeros.infrastructure.metrics_query_repositories import SqlAlchemyMetricsSourceLoader

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]


def _require_session(uow: IntegratedUnitOfWork) -> AsyncSession:
    if not isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
        raise MetricsRecalculateHandlerError(
            error_code=OutboxErrorCode.HANDLER_FAILED,
            permanent=True,
        )
    return uow.session


class MetricsRecalculateHandlerError(Exception):
    def __init__(self, *, error_code: OutboxErrorCode, permanent: bool) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("metrics recalculation failed")


class MetricsRecalculateHandler:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        metrics_engine: MetricsEngine,
        service_actor_id: UUID,
        uuid_factory: _UuidFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._metrics_engine = metrics_engine
        self._service_actor_id = service_actor_id
        self._uuid_factory = uuid_factory

    async def handle(self, *, job: OutboxJob) -> None:
        if job.tenant_id is None:
            raise MetricsRecalculateHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )
        uow = self._uow_factory()
        async with uow:
            tenant = await uow.tenants.get_by_id(tenant_id=job.tenant_id)
            if tenant is None:
                raise MetricsRecalculateHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )
            time_zone = tenant.time_zone

        local_date = local_date_from_timestamp(occurred_at=job.created_at, time_zone=time_zone)
        windows = (
            daily_window_for_local_date(local_date=local_date, time_zone=time_zone),
            rolling_30_day_window_for_local_date(local_date=local_date, time_zone=time_zone),
        )
        audit_context = AuditContext(correlation_id=job.id)
        for window in windows:
            await self._calculate_tenant_snapshot(
                job=job,
                window=window,
                audit_context=audit_context,
            )
            await self._calculate_manager_snapshots(
                job=job,
                window=window,
                audit_context=audit_context,
            )

    async def _calculate_tenant_snapshot(
        self,
        *,
        job: OutboxJob,
        window: MetricWindow,
        audit_context: AuditContext,
    ) -> None:
        assert job.tenant_id is not None
        uow = self._uow_factory()
        async with uow:
            existing = await uow.metric_snapshots.get_completed_snapshot(
                tenant_id=job.tenant_id,
                scope=MetricScope.TENANT,
                manager_user_id=None,
                window_start=window.start,
                window_end=window.end,
                formula_version=METRIC_FORMULA_VERSION,
            )
            if existing is not None:
                return
            loader = SqlAlchemyMetricsSourceLoader(_require_session(uow))
            source_data = await loader.load_for_window(
                tenant_id=job.tenant_id,
                window_start=window.start,
                window_end=window.end,
            )
            snapshot = self._metrics_engine.calculate_snapshot(
                snapshot_id=self._uuid_factory(),
                tenant_id=job.tenant_id,
                scope=MetricScope.TENANT,
                manager_user_id=None,
                window=window,
                source_data=source_data,
                computed_at=job.created_at,
            )
            try:
                await uow.metric_snapshots.append_completed(snapshot=snapshot)
                await append_required_audit_event(
                    uow.audit_events,
                    metrics_snapshot_completed_event(
                        tenant_id=job.tenant_id,
                        snapshot_id=snapshot.id,
                        metric_scope=snapshot.scope.value,
                        formula_version=snapshot.formula_version,
                        window_code=window.window_code,
                        affected_count=len(snapshot.values),
                        occurred_at=job.created_at,
                        audit_context=audit_context,
                        actor_type=AuditActorType.SERVICE,
                        actor_id=self._service_actor_id,
                        event_id=self._uuid_factory(),
                    ),
                )
                await uow.commit()
            except DuplicateMetricSnapshotError:
                await uow.rollback()
            except Exception as error:
                await uow.rollback()
                raise MetricsRecalculateHandlerError(
                    error_code=OutboxErrorCode.HANDLER_FAILED,
                    permanent=False,
                ) from error

    async def _calculate_manager_snapshots(
        self,
        *,
        job: OutboxJob,
        window: MetricWindow,
        audit_context: AuditContext,
    ) -> None:
        assert job.tenant_id is not None
        uow = self._uow_factory()
        async with uow:
            loader = SqlAlchemyMetricsSourceLoader(_require_session(uow))
            source_data = await loader.load_for_window(
                tenant_id=job.tenant_id,
                window_start=window.start,
                window_end=window.end,
            )
            manager_ids = {assignment.manager_user_id for assignment in source_data.assignments}

        for manager_user_id in sorted(manager_ids, key=str):
            uow = self._uow_factory()
            async with uow:
                existing = await uow.metric_snapshots.get_completed_snapshot(
                    tenant_id=job.tenant_id,
                    scope=MetricScope.MANAGER,
                    manager_user_id=manager_user_id,
                    window_start=window.start,
                    window_end=window.end,
                    formula_version=METRIC_FORMULA_VERSION,
                )
                if existing is not None:
                    continue
                loader = SqlAlchemyMetricsSourceLoader(_require_session(uow))
                scoped_source = await loader.load_for_window(
                    tenant_id=job.tenant_id,
                    window_start=window.start,
                    window_end=window.end,
                )
                snapshot = self._metrics_engine.calculate_snapshot(
                    snapshot_id=self._uuid_factory(),
                    tenant_id=job.tenant_id,
                    scope=MetricScope.MANAGER,
                    manager_user_id=manager_user_id,
                    window=window,
                    source_data=scoped_source,
                    computed_at=job.created_at,
                )
                try:
                    await uow.metric_snapshots.append_completed(snapshot=snapshot)
                    await append_required_audit_event(
                        uow.audit_events,
                        metrics_snapshot_completed_event(
                            tenant_id=job.tenant_id,
                            snapshot_id=snapshot.id,
                            metric_scope=snapshot.scope.value,
                            formula_version=snapshot.formula_version,
                            window_code=window.window_code,
                            affected_count=len(snapshot.values),
                            occurred_at=job.created_at,
                            audit_context=audit_context,
                            actor_type=AuditActorType.SERVICE,
                            actor_id=self._service_actor_id,
                            event_id=self._uuid_factory(),
                        ),
                    )
                    await uow.commit()
                except DuplicateMetricSnapshotError:
                    await uow.rollback()
                except Exception as error:
                    await uow.rollback()
                    raise MetricsRecalculateHandlerError(
                        error_code=OutboxErrorCode.HANDLER_FAILED,
                        permanent=False,
                    ) from error
