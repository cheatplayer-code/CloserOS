"""Application ports for persisted TOTP MFA enrollments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserMfaTotpEnrollment:
    user_id: UUID
    secret_tenant_id: UUID
    encrypted_secret_content_id: UUID
    last_accepted_timestep: int | None
    created_at: datetime
    updated_at: datetime


class UserMfaTotpEnrollmentRepository(Protocol):
    async def get_by_user_id(self, *, user_id: UUID) -> UserMfaTotpEnrollment | None: ...

    async def upsert(
        self,
        *,
        user_id: UUID,
        secret_tenant_id: UUID,
        encrypted_secret_content_id: UUID,
        created_at: datetime,
        updated_at: datetime,
    ) -> None: ...

    async def update_last_accepted_timestep(
        self,
        *,
        user_id: UUID,
        last_accepted_timestep: int,
        updated_at: datetime,
    ) -> None: ...


__all__ = [
    "UserMfaTotpEnrollment",
    "UserMfaTotpEnrollmentRepository",
]
