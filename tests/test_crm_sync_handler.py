from __future__ import annotations

import asyncio
from dataclasses import dataclass

from closeros.application.crm_sync_handler import CrmSyncHandler
from closeros.domain.outbox import OutboxJob, OutboxJobKind, OutboxJobReference, OutboxJobState

from tests.xy_crm_support import CRM_CONNECTION_ID, NOW, TENANT_ID


@dataclass
class _CaptureSyncService:
    calls: list[tuple[object, object]]

    async def sync_once(self, *, tenant_id: object, connection_id: object) -> None:
        self.calls.append((tenant_id, connection_id))


def test_crm_sync_handler_dispatches_tenant_scoped_job() -> None:
    service = _CaptureSyncService(calls=[])
    handler = CrmSyncHandler(sync_service=service)  # type: ignore[arg-type]
    job = OutboxJob(
        id=CRM_CONNECTION_ID,
        tenant_id=TENANT_ID,
        job_kind=OutboxJobKind.CRM_SYNC,
        reference=OutboxJobReference(
            resource_type="crm_connection",
            resource_id=CRM_CONNECTION_ID,
            schema_version=1,
            tenant_id=TENANT_ID,
        ),
        deduplication_key="crm-sync-test",
        priority=100,
        state=OutboxJobState.PUBLISHED,
        available_at=NOW,
        created_at=NOW,
        attempt_count=0,
        max_attempts=3,
        version=1,
    )

    asyncio.run(handler.handle(job=job))

    assert service.calls == [(TENANT_ID, CRM_CONNECTION_ID)]
