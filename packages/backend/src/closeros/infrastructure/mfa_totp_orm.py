"""SQLAlchemy ORM model for TOTP MFA enrollments."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, Integer
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.infrastructure.orm_base import Base


class UserMfaTotpEnrollmentRow(Base):
    __tablename__ = "user_mfa_totp_enrollments"

    user_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    secret_tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    encrypted_secret_content_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    last_accepted_timestep: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_mfa_totp_enrollments_user_id"
        ),
        ForeignKeyConstraint(
            ["secret_tenant_id", "encrypted_secret_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            name="fk_user_mfa_totp_enrollments_secret_content",
        ),
    )


__all__ = ["UserMfaTotpEnrollmentRow"]
