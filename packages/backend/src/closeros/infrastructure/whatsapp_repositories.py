"""PostgreSQL repositories for WhatsApp Cloud connections."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.whatsapp_persistence import (
    DuplicateWhatsAppConnectionError,
    WhatsAppCloudConnectionRecord,
    WhatsAppConnectionNotFoundError,
    WhatsAppConnectionVersionConflictError,
    WhatsAppPersistenceError,
)
from closeros.infrastructure import whatsapp_mappers as mappers
from closeros.infrastructure.persistence_errors import translate_integrity_error
from closeros.infrastructure.repository_helpers import tenant_scoped_get
from closeros.infrastructure.whatsapp_orm import WhatsAppCloudConnectionRow


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise translate_integrity_error(
            error,
            constraint_errors={
                "uq_whatsapp_cloud_connections_tenant_id_phone_number_id": (
                    DuplicateWhatsAppConnectionError
                ),
                "uq_whatsapp_cloud_connections_webhook_public_key": (
                    DuplicateWhatsAppConnectionError
                ),
            },
            default=WhatsAppPersistenceError,
            message="whatsapp connection persistence integrity error",
        ) from error


class SqlAlchemyWhatsAppCloudConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, record: WhatsAppCloudConnectionRecord) -> None:
        self._session.add(mappers.record_to_row(record))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> WhatsAppCloudConnectionRecord | None:
        row = await tenant_scoped_get(
            self._session,
            WhatsAppCloudConnectionRow,
            tenant_id=tenant_id,
            record_id=connection_id,
        )
        return None if row is None else mappers.row_to_record(row)

    async def get_by_id_for_update(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> WhatsAppCloudConnectionRecord | None:
        statement = (
            select(WhatsAppCloudConnectionRow)
            .where(
                WhatsAppCloudConnectionRow.tenant_id == tenant_id,
                WhatsAppCloudConnectionRow.id == connection_id,
            )
            .with_for_update()
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.row_to_record(row)

    async def get_by_webhook_public_key(
        self,
        *,
        webhook_public_key: str,
    ) -> WhatsAppCloudConnectionRecord | None:
        statement = select(WhatsAppCloudConnectionRow).where(
            WhatsAppCloudConnectionRow.webhook_public_key == webhook_public_key
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.row_to_record(row)

    async def list_by_tenant(
        self,
        *,
        tenant_id: UUID,
    ) -> tuple[WhatsAppCloudConnectionRecord, ...]:
        statement = (
            select(WhatsAppCloudConnectionRow)
            .where(WhatsAppCloudConnectionRow.tenant_id == tenant_id)
            .order_by(WhatsAppCloudConnectionRow.created_at.desc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.row_to_record(row) for row in rows)

    async def update(
        self,
        *,
        record: WhatsAppCloudConnectionRecord,
        expected_version: int,
    ) -> WhatsAppCloudConnectionRecord:
        row = (
            await self._session.execute(
                select(WhatsAppCloudConnectionRow)
                .where(
                    WhatsAppCloudConnectionRow.tenant_id == record.tenant_id,
                    WhatsAppCloudConnectionRow.id == record.id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise WhatsAppConnectionNotFoundError("whatsapp connection not found")
        if row.version != expected_version:
            raise WhatsAppConnectionVersionConflictError("whatsapp connection version conflict")
        row.app_id = record.app_id
        row.waba_id = record.waba_id
        row.phone_number_id = record.phone_number_id
        row.display_phone_number = record.display_phone_number
        row.graph_api_version = record.graph_api_version
        row.access_token_ref = record.access_token_ref
        row.app_secret_ref = record.app_secret_ref
        row.verify_token_ref = record.verify_token_ref
        row.status = record.status.value
        row.webhook_subscription_status = record.webhook_subscription_status.value
        row.capabilities = [
            capability.value
            for capability in sorted(record.capabilities, key=lambda item: item.value)
        ]
        row.webhook_public_key = record.webhook_public_key
        row.updated_at = record.updated_at
        row.last_verified_at = record.last_verified_at
        row.version = record.version
        await _flush(self._session)
        return mappers.row_to_record(row)
