"""SQLAlchemy repository for TOTP MFA enrollments."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.mfa_persistence import UserMfaTotpEnrollment
from closeros.application.persistence_errors import PersistenceError
from closeros.infrastructure.mfa_totp_orm import UserMfaTotpEnrollmentRow
from closeros.infrastructure.persistence_errors import translate_integrity_error


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise translate_integrity_error(
            error,
            constraint_errors={},
            default=PersistenceError,
            message="mfa enrollment persistence integrity error",
        ) from error


def _row_to_domain(row: UserMfaTotpEnrollmentRow) -> UserMfaTotpEnrollment:
    return UserMfaTotpEnrollment(
        user_id=row.user_id,
        secret_tenant_id=row.secret_tenant_id,
        encrypted_secret_content_id=row.encrypted_secret_content_id,
        last_accepted_timestep=row.last_accepted_timestep,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyUserMfaTotpEnrollmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, *, user_id: UUID) -> UserMfaTotpEnrollment | None:
        statement = select(UserMfaTotpEnrollmentRow).where(
            UserMfaTotpEnrollmentRow.user_id == user_id
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else _row_to_domain(row)

    async def upsert(
        self,
        *,
        user_id: UUID,
        secret_tenant_id: UUID,
        encrypted_secret_content_id: UUID,
        created_at: datetime,
        updated_at: datetime,
    ) -> None:
        statement = insert(UserMfaTotpEnrollmentRow).values(
            user_id=user_id,
            secret_tenant_id=secret_tenant_id,
            encrypted_secret_content_id=encrypted_secret_content_id,
            last_accepted_timestep=None,
            created_at=created_at,
            updated_at=updated_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[UserMfaTotpEnrollmentRow.user_id],
            set_={
                "secret_tenant_id": secret_tenant_id,
                "encrypted_secret_content_id": encrypted_secret_content_id,
                "updated_at": updated_at,
            },
        )
        await self._session.execute(statement)
        await _flush(self._session)

    async def update_last_accepted_timestep(
        self,
        *,
        user_id: UUID,
        last_accepted_timestep: int,
        updated_at: datetime,
    ) -> None:
        statement = (
            update(UserMfaTotpEnrollmentRow)
            .where(UserMfaTotpEnrollmentRow.user_id == user_id)
            .values(
                last_accepted_timestep=last_accepted_timestep,
                updated_at=updated_at,
            )
        )
        result = await self._session.execute(statement)
        if cast(Any, result).rowcount == 0:
            raise PersistenceError("mfa enrollment not found")
        await _flush(self._session)


__all__ = ["SqlAlchemyUserMfaTotpEnrollmentRepository"]
