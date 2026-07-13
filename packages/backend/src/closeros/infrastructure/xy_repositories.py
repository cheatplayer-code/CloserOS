"""PostgreSQL repositories for XY production operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.notification_ports import (
    NotificationDeliveryAttemptRecord,
    NotificationDeliveryNotFoundError,
)
from closeros.application.persistence_errors import PersistenceError
from closeros.application.retention_persistence import (
    LegalHoldNotFoundError,
    RetentionPurgeRunNotFoundError,
)
from closeros.domain.legal_hold import LegalHold, LegalHoldStatus
from closeros.domain.notification import NotificationDelivery, NotificationDeliveryStatus
from closeros.domain.provider_media_reference import MediaQuarantineStatus
from closeros.domain.retention_execution import (
    RetentionPurgeBatch,
    RetentionPurgeBatchStatus,
    RetentionPurgeRun,
    RetentionPurgeRunStatus,
)
from closeros.infrastructure import xy_mappers as mappers
from closeros.infrastructure.outbound_orm import ProviderMediaReferenceRow
from closeros.infrastructure.persistence_errors import translate_integrity_error
from closeros.infrastructure.xy_orm import (
    LegalHoldRow,
    NotificationDeliveryRow,
    RetentionPurgeBatchRow,
    RetentionPurgeRunRow,
)


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise translate_integrity_error(
            error,
            constraint_errors={},
            default=PersistenceError,
            message="xy persistence integrity error",
        ) from error


async def acquire_tenant_retention_lock(session: AsyncSession, *, tenant_id: UUID) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant_id, 0))"),
        {"tenant_id": str(tenant_id)},
    )


class SqlAlchemyNotificationDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, delivery: NotificationDelivery) -> None:
        self._session.add(mappers.notification_delivery_to_row(delivery))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID | None,
        delivery_id: UUID,
    ) -> NotificationDelivery | None:
        statement = select(NotificationDeliveryRow).where(
            NotificationDeliveryRow.id == delivery_id,
        )
        if tenant_id is not None:
            statement = statement.where(NotificationDeliveryRow.tenant_id == tenant_id)
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.notification_delivery_row_to_domain(row)

    async def update_status(
        self,
        *,
        tenant_id: UUID | None,
        delivery_id: UUID,
        status: NotificationDeliveryStatus,
        updated_at: datetime,
        delivered_at: datetime | None = None,
        last_error_code: str | None = None,
        attempt_count: int | None = None,
        clear_encrypted_payload_content_id: bool = False,
    ) -> None:
        values: dict[str, object] = {
            "status": status.value,
            "updated_at": updated_at,
            "delivered_at": delivered_at,
            "last_error_code": last_error_code,
        }
        if attempt_count is not None:
            values["attempt_count"] = attempt_count
        if clear_encrypted_payload_content_id:
            values["encrypted_payload_content_id"] = None
        statement = (
            update(NotificationDeliveryRow)
            .where(NotificationDeliveryRow.id == delivery_id)
            .values(**values)
        )
        if tenant_id is not None:
            statement = statement.where(NotificationDeliveryRow.tenant_id == tenant_id)
        result = await self._session.execute(statement)
        if cast(Any, result).rowcount == 0:
            raise NotificationDeliveryNotFoundError("notification delivery not found")
        await _flush(self._session)


class SqlAlchemyNotificationDeliveryAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, attempt: NotificationDeliveryAttemptRecord) -> None:
        self._session.add(mappers.notification_attempt_to_row(attempt))
        await _flush(self._session)


class SqlAlchemyLegalHoldRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, legal_hold: LegalHold) -> None:
        await acquire_tenant_retention_lock(self._session, tenant_id=legal_hold.tenant_id)
        self._session.add(mappers.legal_hold_to_row(legal_hold))
        await _flush(self._session)

    async def get_active_for_tenant(self, *, tenant_id: UUID) -> LegalHold | None:
        statement = (
            select(LegalHoldRow)
            .where(
                LegalHoldRow.tenant_id == tenant_id,
                LegalHoldRow.status == LegalHoldStatus.ACTIVE.value,
            )
            .order_by(LegalHoldRow.created_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.legal_hold_row_to_domain(row)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        legal_hold_id: UUID,
    ) -> LegalHold | None:
        statement = select(LegalHoldRow).where(
            LegalHoldRow.tenant_id == tenant_id,
            LegalHoldRow.id == legal_hold_id,
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.legal_hold_row_to_domain(row)

    async def update(self, *, legal_hold: LegalHold) -> None:
        await acquire_tenant_retention_lock(self._session, tenant_id=legal_hold.tenant_id)
        statement = (
            update(LegalHoldRow)
            .where(
                LegalHoldRow.tenant_id == legal_hold.tenant_id,
                LegalHoldRow.id == legal_hold.id,
            )
            .values(
                status=legal_hold.status.value,
                reason_code=legal_hold.reason_code,
                reason_detail=legal_hold.reason_detail,
                released_by_user_id=legal_hold.released_by_user_id,
                released_at=legal_hold.released_at,
                updated_at=legal_hold.updated_at,
            )
        )
        result = await self._session.execute(statement)
        if cast(Any, result).rowcount == 0:
            raise LegalHoldNotFoundError("legal hold not found")
        await _flush(self._session)

    async def tenant_has_active_hold(self, *, tenant_id: UUID) -> bool:
        return await self.get_active_for_tenant(tenant_id=tenant_id) is not None


class SqlAlchemyRetentionPurgeRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, purge_run: RetentionPurgeRun) -> None:
        self._session.add(mappers.retention_purge_run_to_row(purge_run))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        purge_run_id: UUID,
    ) -> RetentionPurgeRun | None:
        statement = select(RetentionPurgeRunRow).where(
            RetentionPurgeRunRow.tenant_id == tenant_id,
            RetentionPurgeRunRow.id == purge_run_id,
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.retention_purge_run_row_to_domain(row)

    async def update(self, *, purge_run: RetentionPurgeRun) -> None:
        statement = (
            update(RetentionPurgeRunRow)
            .where(
                RetentionPurgeRunRow.tenant_id == purge_run.tenant_id,
                RetentionPurgeRunRow.id == purge_run.id,
            )
            .values(
                status=purge_run.status.value,
                items_scanned=purge_run.items_scanned,
                items_deleted=purge_run.items_deleted,
                items_skipped_legal_hold=purge_run.items_skipped_legal_hold,
                started_at=purge_run.started_at,
                completed_at=purge_run.completed_at,
                last_error_code=purge_run.last_error_code,
                claim_token=purge_run.claim_token,
                claim_expires_at=purge_run.claim_expires_at,
                version=purge_run.version,
                updated_at=purge_run.updated_at,
            )
        )
        result = await self._session.execute(statement)
        if cast(Any, result).rowcount == 0:
            raise RetentionPurgeRunNotFoundError("retention purge run not found")
        await _flush(self._session)

    async def try_claim(
        self,
        *,
        tenant_id: UUID,
        purge_run_id: UUID,
        claim_token: UUID,
        claim_expires_at: datetime,
        now: datetime,
        expected_version: int | None = None,
    ) -> RetentionPurgeRun | None:
        conditions = [
            RetentionPurgeRunRow.tenant_id == tenant_id,
            RetentionPurgeRunRow.id == purge_run_id,
            RetentionPurgeRunRow.status.in_(
                (
                    RetentionPurgeRunStatus.PENDING.value,
                    RetentionPurgeRunStatus.RUNNING.value,
                )
            ),
            or_(
                RetentionPurgeRunRow.claim_token.is_(None),
                RetentionPurgeRunRow.claim_expires_at.is_(None),
                RetentionPurgeRunRow.claim_expires_at <= now,
                RetentionPurgeRunRow.claim_token == claim_token,
            ),
        ]
        if expected_version is not None:
            conditions.append(RetentionPurgeRunRow.version == expected_version)
        statement = (
            update(RetentionPurgeRunRow)
            .where(*conditions)
            .values(
                claim_token=claim_token,
                claim_expires_at=claim_expires_at,
                status=RetentionPurgeRunStatus.RUNNING.value,
                started_at=func.coalesce(RetentionPurgeRunRow.started_at, now),
                version=RetentionPurgeRunRow.version + 1,
                updated_at=now,
            )
            .returning(RetentionPurgeRunRow)
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        await _flush(self._session)
        return None if row is None else mappers.retention_purge_run_row_to_domain(row)

    async def renew_claim(
        self,
        *,
        tenant_id: UUID,
        purge_run_id: UUID,
        claim_token: UUID,
        claim_expires_at: datetime,
        now: datetime,
        expected_version: int,
    ) -> RetentionPurgeRun | None:
        statement = (
            update(RetentionPurgeRunRow)
            .where(
                RetentionPurgeRunRow.tenant_id == tenant_id,
                RetentionPurgeRunRow.id == purge_run_id,
                RetentionPurgeRunRow.claim_token == claim_token,
                RetentionPurgeRunRow.claim_expires_at > now,
                RetentionPurgeRunRow.version == expected_version,
            )
            .values(
                claim_expires_at=claim_expires_at,
                version=RetentionPurgeRunRow.version + 1,
                updated_at=now,
            )
            .returning(RetentionPurgeRunRow)
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        await _flush(self._session)
        return None if row is None else mappers.retention_purge_run_row_to_domain(row)

    async def list_for_tenant(
        self,
        *,
        tenant_id: UUID,
        limit: int = 20,
    ) -> tuple[RetentionPurgeRun, ...]:
        statement = (
            select(RetentionPurgeRunRow)
            .where(RetentionPurgeRunRow.tenant_id == tenant_id)
            .order_by(RetentionPurgeRunRow.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.retention_purge_run_row_to_domain(row) for row in rows)

    async def acquire_tenant_retention_lock(self, *, tenant_id: UUID) -> None:
        await acquire_tenant_retention_lock(self._session, tenant_id=tenant_id)


class SqlAlchemyRetentionPurgeBatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, batch: RetentionPurgeBatch) -> None:
        self._session.add(mappers.retention_purge_batch_to_row(batch))
        await _flush(self._session)

    async def list_for_run(
        self,
        *,
        tenant_id: UUID,
        purge_run_id: UUID,
    ) -> tuple[RetentionPurgeBatch, ...]:
        statement = select(RetentionPurgeBatchRow).where(
            RetentionPurgeBatchRow.tenant_id == tenant_id,
            RetentionPurgeBatchRow.purge_run_id == purge_run_id,
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.retention_purge_batch_row_to_domain(row) for row in rows)

    async def update_status(
        self,
        *,
        tenant_id: UUID,
        batch_id: UUID,
        status: RetentionPurgeBatchStatus,
        completed_at: datetime | None,
    ) -> None:
        statement = (
            update(RetentionPurgeBatchRow)
            .where(
                RetentionPurgeBatchRow.tenant_id == tenant_id,
                RetentionPurgeBatchRow.id == batch_id,
            )
            .values(status=status.value, completed_at=completed_at)
        )
        await self._session.execute(statement)
        await _flush(self._session)


async def update_provider_media_status(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    media_reference_id: UUID,
    quarantine_status: MediaQuarantineStatus,
    updated_at: datetime,
    mime_type: str | None = None,
    size_bytes: int | None = None,
    encrypted_content_id: UUID | None = None,
    clear_encrypted_content_id: bool = False,
) -> None:
    values: dict[str, object] = {
        "quarantine_status": quarantine_status.value,
        "updated_at": updated_at,
    }
    if mime_type is not None:
        values["mime_type"] = mime_type
    if size_bytes is not None:
        values["size_bytes"] = size_bytes
    if encrypted_content_id is not None:
        values["encrypted_content_id"] = encrypted_content_id
    if clear_encrypted_content_id:
        values["encrypted_content_id"] = None
    statement = (
        update(ProviderMediaReferenceRow)
        .where(
            ProviderMediaReferenceRow.tenant_id == tenant_id,
            ProviderMediaReferenceRow.id == media_reference_id,
        )
        .values(**values)
    )
    await session.execute(statement)
    await _flush(session)
