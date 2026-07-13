"""Outbox handler for CRM sync jobs."""

from __future__ import annotations

from dataclasses import dataclass

from closeros.application.crm_sync_service import CrmSyncService, CrmSyncServiceError
from closeros.domain.outbox import OutboxErrorCode, OutboxJob


class CrmSyncHandlerError(Exception):
    def __init__(self, *, error_code: OutboxErrorCode, permanent: bool) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("crm sync failed")


@dataclass(frozen=True, slots=True)
class CrmSyncHandler:
    sync_service: CrmSyncService

    async def handle(self, *, job: OutboxJob) -> None:
        if job.tenant_id is None:
            raise CrmSyncHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )
        try:
            await self.sync_service.sync_once(
                tenant_id=job.tenant_id,
                connection_id=job.reference.resource_id,
            )
        except CrmSyncServiceError as error:
            raise CrmSyncHandlerError(
                error_code=OutboxErrorCode.HANDLER_FAILED,
                permanent=False,
            ) from error


__all__ = ["CrmSyncHandler", "CrmSyncHandlerError"]
