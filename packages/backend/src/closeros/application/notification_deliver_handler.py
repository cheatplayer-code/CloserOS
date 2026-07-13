"""Outbox handler for notification.deliver jobs."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from closeros.application.audit_recording import AuditContext
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.notification_delivery_service import NotificationDeliveryService
from closeros.application.notification_ports import (
    NotificationSender,
    NotificationSenderError,
    NotificationSenderTransientError,
)
from closeros.domain.notification import NotificationDeliveryStatus
from closeros.domain.outbox import OutboxErrorCode, OutboxJob

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]


class NotificationDeliverHandlerError(Exception):
    def __init__(self, *, error_code: OutboxErrorCode, permanent: bool) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("notification delivery failed")


class NotificationDeliverHandler:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        delivery_service: NotificationDeliveryService,
        sender: NotificationSender,
        service_actor_id: UUID,
    ) -> None:
        self._uow_factory = uow_factory
        self._delivery_service = delivery_service
        self._sender = sender
        self._service_actor_id = service_actor_id

    async def handle(self, *, job: OutboxJob) -> None:
        reference = job.reference
        if reference.resource_type != "notification_delivery":
            raise NotificationDeliverHandlerError(
                error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                permanent=True,
            )

        uow = self._uow_factory()
        async with uow:
            delivery = await uow.notification_deliveries.get_by_id(
                tenant_id=job.tenant_id,
                delivery_id=reference.resource_id,
            )
            if delivery is None:
                raise NotificationDeliverHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )
            if delivery.status is NotificationDeliveryStatus.SUCCEEDED:
                return

        occurred_at = job.processing_started_at or job.created_at
        audit_context = AuditContext(correlation_id=job.id)
        try:
            await self._delivery_service.deliver_pending(
                tenant_id=job.tenant_id,
                delivery_id=reference.resource_id,
                sender=self._sender,
                occurred_at=occurred_at,
                audit_context=audit_context,
            )
        except NotificationDeliverHandlerError:
            raise
        except NotificationSenderTransientError as exc:
            raise NotificationDeliverHandlerError(
                error_code=OutboxErrorCode.ADAPTER_UNAVAILABLE,
                permanent=False,
            ) from exc
        except NotificationSenderError as exc:
            raise NotificationDeliverHandlerError(
                error_code=OutboxErrorCode.ADAPTER_UNAVAILABLE,
                permanent=True,
            ) from exc
        except Exception as exc:
            raise NotificationDeliverHandlerError(
                error_code=OutboxErrorCode.ADAPTER_UNAVAILABLE,
                permanent=False,
            ) from exc


__all__ = ["NotificationDeliverHandler", "NotificationDeliverHandlerError"]
