"""Fail-closed synthetic demo reset bounded to provenance resource IDs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from uuid import UUID, uuid4

from sqlalchemy import text

from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.domain.synthetic_seed import (
    RESOURCE_DELETION_ORDER,
    SyntheticResetPlan,
    SyntheticSeedResetState,
    SyntheticSeedResourceType,
)
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]

_TABLE_BY_TYPE: dict[SyntheticSeedResourceType, str] = {
    SyntheticSeedResourceType.FINDING_EVIDENCE: "conversation_finding_evidence",
    SyntheticSeedResourceType.FINDING: "conversation_findings",
    SyntheticSeedResourceType.ANALYSIS_RUN: "conversation_analysis_runs",
    SyntheticSeedResourceType.SANITIZATION: "content_sanitizations",
    SyntheticSeedResourceType.OUTBOX_JOB: "outbox_jobs",
    SyntheticSeedResourceType.FOLLOW_UP_TASK: "follow_up_tasks",
    SyntheticSeedResourceType.MESSAGE: "messages",
    SyntheticSeedResourceType.MANAGER_ASSIGNMENT: "manager_assignments",
    SyntheticSeedResourceType.CRM_OUTCOME: "crm_outcomes",
    SyntheticSeedResourceType.METRIC_SNAPSHOT: "metric_snapshots",
    SyntheticSeedResourceType.ENCRYPTED_CONTENT: "encrypted_contents",
    SyntheticSeedResourceType.CONVERSATION_THREAD: "conversation_threads",
    SyntheticSeedResourceType.SALES_CASE: "sales_cases",
    SyntheticSeedResourceType.LEAD: "leads",
    SyntheticSeedResourceType.CHANNEL_CONNECTION: "channel_connections",
    SyntheticSeedResourceType.TENANT_AI_POLICY: "tenant_ai_policies",
    SyntheticSeedResourceType.MEMBERSHIP: "memberships",
    SyntheticSeedResourceType.USER: "users",
}


class SyntheticDemoResetError(Exception):
    """Base class for synthetic reset failures."""


class SyntheticDemoResetService:
    def __init__(self, *, uow_factory: _UnitOfWorkFactory, seed_version: str) -> None:
        self._uow_factory = uow_factory
        self._seed_version = seed_version

    async def plan_reset(self, *, tenant_id: UUID) -> SyntheticResetPlan | None:
        uow = self._uow_factory()
        async with uow:
            manifest = await uow.synthetic_seed_manifests.get_active_for_tenant(
                tenant_id=tenant_id,
                seed_version=self._seed_version,
            )
            if manifest is None:
                return None
            resources = await uow.synthetic_seed_resources.list_for_manifest(
                tenant_id=tenant_id,
                manifest_id=manifest.id,
            )
        counts: dict[str, int] = defaultdict(int)
        for resource in resources:
            counts[resource.resource_type.value] += 1
        return SyntheticResetPlan(
            tenant_id=tenant_id,
            manifest_id=manifest.id,
            counts_by_type=dict(sorted(counts.items())),
            total_resources=len(resources),
        )

    async def reset(
        self,
        *,
        tenant_id: UUID,
        dry_run: bool = False,
    ) -> SyntheticResetPlan:
        plan = await self.plan_reset(tenant_id=tenant_id)
        if plan is None:
            raise SyntheticDemoResetError(
                "no active synthetic seed manifest for tenant; reset refuses to proceed"
            )
        if dry_run:
            return plan

        uow = self._uow_factory()
        async with uow:
            if not isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
                raise SyntheticDemoResetError("reset requires integrated SQLAlchemy unit of work")
            marked = await uow.synthetic_seed_manifests.mark_reset_state(
                tenant_id=tenant_id,
                manifest_id=plan.manifest_id,
                reset_state=SyntheticSeedResetState.RESETTING,
                expected_state=SyntheticSeedResetState.ACTIVE,
            )
            if marked is None:
                raise SyntheticDemoResetError(
                    "synthetic seed manifest is not active or already being reset"
                )
            resources = await uow.synthetic_seed_resources.list_for_manifest(
                tenant_id=tenant_id,
                manifest_id=plan.manifest_id,
            )
            if not resources:
                raise SyntheticDemoResetError(
                    "active synthetic seed manifest has no registered resources; failing closed"
                )

            by_type: dict[SyntheticSeedResourceType, list[UUID]] = defaultdict(list)
            for resource in resources:
                if resource.tenant_id != tenant_id:
                    raise SyntheticDemoResetError("cross-tenant resource rejected")
                by_type[resource.resource_type].append(resource.resource_id)

            ordered_types = sorted(
                by_type.keys(),
                key=lambda item: RESOURCE_DELETION_ORDER.get(item, 0),
                reverse=True,
            )
            for resource_type in ordered_types:
                ids = by_type[resource_type]
                await self._delete_scoped(
                    uow=uow,
                    tenant_id=tenant_id,
                    resource_type=resource_type,
                    resource_ids=ids,
                )

            await uow.synthetic_seed_resources.delete_for_manifest(
                tenant_id=tenant_id,
                manifest_id=plan.manifest_id,
            )
            completed = await uow.synthetic_seed_manifests.mark_reset_state(
                tenant_id=tenant_id,
                manifest_id=plan.manifest_id,
                reset_state=SyntheticSeedResetState.RESET,
                expected_state=SyntheticSeedResetState.RESETTING,
            )
            if completed is None:
                raise SyntheticDemoResetError("failed to finalize synthetic seed reset state")
            await uow.commit()
        return plan

    async def _delete_scoped(
        self,
        *,
        uow: SqlAlchemyIntegratedUnitOfWork,
        tenant_id: UUID,
        resource_type: SyntheticSeedResourceType,
        resource_ids: list[UUID],
    ) -> None:
        if not resource_ids:
            return
        if resource_type is SyntheticSeedResourceType.OUTBOX_JOB:
            await uow.session.execute(
                text("DELETE FROM outbox_job_attempts WHERE job_id = ANY(:ids)"),
                {"ids": resource_ids},
            )
            await uow.session.execute(
                text("DELETE FROM outbox_jobs WHERE tenant_id = :tenant_id AND id = ANY(:ids)"),
                {"tenant_id": tenant_id, "ids": resource_ids},
            )
            return
        if resource_type is SyntheticSeedResourceType.SANITIZATION:
            await uow.session.execute(
                text(
                    "DELETE FROM content_sanitization_category_counts "
                    "WHERE sanitization_id = ANY(:ids)"
                ),
                {"ids": resource_ids},
            )
            await uow.session.execute(
                text(
                    "DELETE FROM content_sanitizations "
                    "WHERE tenant_id = :tenant_id AND id = ANY(:ids)"
                ),
                {"tenant_id": tenant_id, "ids": resource_ids},
            )
            return
        if resource_type is SyntheticSeedResourceType.METRIC_SNAPSHOT:
            await uow.session.execute(
                text(
                    "DELETE FROM metric_values WHERE tenant_id = :tenant_id "
                    "AND snapshot_id = ANY(:ids)"
                ),
                {"tenant_id": tenant_id, "ids": resource_ids},
            )
            await uow.session.execute(
                text(
                    "DELETE FROM metric_snapshots WHERE tenant_id = :tenant_id AND id = ANY(:ids)"
                ),
                {"tenant_id": tenant_id, "ids": resource_ids},
            )
            return
        if resource_type is SyntheticSeedResourceType.USER:
            await uow.session.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"),
                {"ids": resource_ids},
            )
            return

        table = _TABLE_BY_TYPE.get(resource_type)
        if table is None:
            raise SyntheticDemoResetError(f"unsupported resource type: {resource_type}")
        await uow.session.execute(
            text(f"DELETE FROM {table} WHERE tenant_id = :tenant_id AND id = ANY(:ids)"),
            {"tenant_id": tenant_id, "ids": resource_ids},
        )


def new_resource_row_id() -> UUID:
    return uuid4()


__all__ = [
    "SyntheticDemoResetError",
    "SyntheticDemoResetService",
    "new_resource_row_id",
]
