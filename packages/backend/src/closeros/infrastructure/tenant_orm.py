"""SQLAlchemy ORM models for tenant, membership, and invitation persistence."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.domain.identity import (
    InvitationStatus,
    MembershipStatus,
    Role,
    TenantStatus,
)
from closeros.infrastructure.orm_base import Base


def _quoted_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_TENANT_STATUS_VALUES = tuple(status.value for status in TenantStatus)
_MEMBERSHIP_STATUS_VALUES = tuple(status.value for status in MembershipStatus)
_INVITATION_STATUS_VALUES = tuple(status.value for status in InvitationStatus)
_ROLE_VALUES = tuple(role.value for role in Role)


class TenantRow(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    time_zone: Mapped[str] = mapped_column(Text, nullable=False)
    raw_message_days: Mapped[int] = mapped_column(Integer, nullable=False)
    sanitized_message_days: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_output_days: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_log_days: Mapped[int] = mapped_column(Integer, nullable=False)
    backup_days: Mapped[int] = mapped_column(Integer, nullable=False)
    post_contract_deletion_days: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"status IN ({_quoted_values(_TENANT_STATUS_VALUES)})",
            name="status",
        ),
        CheckConstraint("raw_message_days >= 0", name="raw_message_days"),
        CheckConstraint("sanitized_message_days >= 0", name="sanitized_message_days"),
        CheckConstraint("ai_output_days >= 0", name="ai_output_days"),
        CheckConstraint("audit_log_days >= 0", name="audit_log_days"),
        CheckConstraint("backup_days >= 0", name="backup_days"),
        CheckConstraint("post_contract_deletion_days >= 0", name="post_contract_deletion_days"),
        Index("ix_tenants_status", "status"),
    )


class MembershipRow(Base):
    __tablename__ = "memberships"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="tenant_id_user_id"),
        CheckConstraint(
            f"status IN ({_quoted_values(_MEMBERSHIP_STATUS_VALUES)})",
            name="status",
        ),
        Index("ix_memberships_tenant_id", "tenant_id"),
        Index("ix_memberships_user_id", "user_id"),
        Index("ix_memberships_tenant_id_status", "tenant_id", "status"),
    )


class MembershipRoleRow(Base):
    __tablename__ = "membership_roles"

    membership_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("membership_id", "role", name="pk_membership_roles"),
        CheckConstraint(
            f"role IN ({_quoted_values(_ROLE_VALUES)})",
            name="role",
        ),
        Index("ix_membership_roles_membership_id", "membership_id"),
    )


class InvitationRow(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"status IN ({_quoted_values(_INVITATION_STATUS_VALUES)})",
            name="status",
        ),
        Index("ix_invitations_tenant_id", "tenant_id"),
        Index("ix_invitations_tenant_id_status", "tenant_id", "status"),
        Index("ix_invitations_expires_at", "expires_at"),
    )


class InvitationRoleRow(Base):
    __tablename__ = "invitation_roles"

    invitation_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("invitations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("invitation_id", "role", name="pk_invitation_roles"),
        CheckConstraint(
            f"role IN ({_quoted_values(_ROLE_VALUES)})",
            name="role",
        ),
        Index("ix_invitation_roles_invitation_id", "invitation_id"),
    )
