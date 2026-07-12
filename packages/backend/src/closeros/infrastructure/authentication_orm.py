"""SQLAlchemy ORM models for the authentication subsystem.

These models are the only representation that touches the database. They are
never returned outside the infrastructure layer; repositories map them to and
from framework-independent domain objects.

Enumerated columns use text with CHECK constraints that mirror the domain
enums, and the session table enforces the same valid stage/assurance/MFA
combinations that the domain entity enforces.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import BYTEA, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.domain.authentication import (
    AuthenticationAssuranceLevel,
    AuthenticationSessionStage,
    AuthenticationTokenPurpose,
)
from closeros.domain.identity import UserStatus
from closeros.infrastructure.orm_base import Base

TOKEN_HASH_BYTES = 32


def _quoted_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_USER_STATUS_VALUES = tuple(status.value for status in UserStatus)
_STAGE_VALUES = tuple(stage.value for stage in AuthenticationSessionStage)
_ASSURANCE_VALUES = tuple(level.value for level in AuthenticationAssuranceLevel)
_PURPOSE_VALUES = tuple(purpose.value for purpose in AuthenticationTokenPurpose)

_STAGE_ASSURANCE_MFA_CHECK = (
    "("
    "stage = 'pending_mfa' AND assurance_level = 'single_factor' "
    "AND mfa_completed = false"
    ") OR ("
    "stage = 'authenticated' AND assurance_level = 'single_factor' "
    "AND mfa_completed = false"
    ") OR ("
    "stage = 'authenticated' AND assurance_level = 'multi_factor' "
    "AND mfa_completed = true"
    ")"
)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"status IN ({_quoted_values(_USER_STATUS_VALUES)})",
            name="status",
        ),
    )


class CredentialRow(Base):
    __tablename__ = "authentication_credentials"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("email", name="email"),
        UniqueConstraint("user_id", name="user_id"),
    )


class SessionRow(Base):
    __tablename__ = "authentication_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    token_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    assurance_level: Mapped[str] = mapped_column(String(32), nullable=False)
    mfa_completed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("token_hash", name="token_hash"),
        CheckConstraint(
            f"octet_length(token_hash) = {TOKEN_HASH_BYTES}",
            name="token_hash_length",
        ),
        CheckConstraint(
            f"stage IN ({_quoted_values(_STAGE_VALUES)})",
            name="stage",
        ),
        CheckConstraint(
            f"assurance_level IN ({_quoted_values(_ASSURANCE_VALUES)})",
            name="assurance_level",
        ),
        CheckConstraint(_STAGE_ASSURANCE_MFA_CHECK, name="stage_assurance_mfa"),
        Index("ix_authentication_sessions_user_id", "user_id"),
        Index("ix_authentication_sessions_expires_at", "expires_at"),
        Index("ix_authentication_sessions_revoked_at", "revoked_at"),
    )


class OneTimeTokenRow(Base):
    __tablename__ = "authentication_one_time_tokens"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("token_hash", name="token_hash"),
        CheckConstraint(
            f"octet_length(token_hash) = {TOKEN_HASH_BYTES}",
            name="token_hash_length",
        ),
        CheckConstraint(
            f"purpose IN ({_quoted_values(_PURPOSE_VALUES)})",
            name="purpose",
        ),
        Index("ix_authentication_one_time_tokens_user_id_purpose", "user_id", "purpose"),
        Index("ix_authentication_one_time_tokens_expires_at", "expires_at"),
    )
