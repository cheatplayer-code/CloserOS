"""Envelope key rewrap service for KMS key rotation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext
from closeros.application.content_encryption_service import (
    ContentEncryptionService,
    ContentEncryptionUnavailableError,
)
from closeros.application.encrypted_content_persistence import EncryptedContentRetentionFilter
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.domain.audit import AuditActorType
from closeros.domain.encrypted_content import EncryptedContentKind

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]


class KmsRewrapUnavailableError(Exception):
    """Raised when key rewrap cannot complete."""


class KmsRewrapService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        content_encryption: ContentEncryptionService,
        service_actor_id: UUID,
        batch_size: int = 100,
    ) -> None:
        self._uow_factory = uow_factory
        self._content_encryption = content_encryption
        self._service_actor_id = service_actor_id
        self._batch_size = batch_size

    async def rewrap_tenant_contents(
        self,
        *,
        tenant_id: UUID,
        kind: EncryptedContentKind,
        occurred_at: datetime,
        correlation_id: UUID,
    ) -> int:
        if self._batch_size < 1:
            raise ValueError("batch_size must be positive")

        uow = self._uow_factory()
        async with uow:
            contents = await uow.encrypted_contents.list_by_tenant_and_kind(
                tenant_id=tenant_id,
                kind=kind,
                limit=self._batch_size,
            )

        rewrapped = 0
        audit_context = AuditContext(correlation_id=correlation_id)
        for content in contents:
            uow = self._uow_factory()
            async with uow:
                try:
                    await self._content_encryption.rewrap_content_key(
                        uow,
                        tenant_id=tenant_id,
                        content_id=content.id,
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                        actor_type=AuditActorType.SERVICE,
                        actor_id=self._service_actor_id,
                        audit_event_id=correlation_id,
                    )
                    await uow.commit()
                except ContentEncryptionUnavailableError as exc:
                    raise KmsRewrapUnavailableError("key rewrap failed") from exc
                rewrapped += 1
        return rewrapped

    async def count_due_for_retention(self, *, expires_before: datetime) -> int:
        uow = self._uow_factory()
        async with uow:
            due = await uow.encrypted_contents.list_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    expires_before=expires_before,
                    limit=self._batch_size,
                )
            )
        return len(due)


__all__ = ["KmsRewrapService", "KmsRewrapUnavailableError"]
