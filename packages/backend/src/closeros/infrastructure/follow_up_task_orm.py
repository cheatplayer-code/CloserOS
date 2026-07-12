"""SQLAlchemy ORM models for follow-up tasks."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.infrastructure.orm_base import Base

_STATUS_VALUES = ("open", "in_progress", "completed", "cancelled")
_PRIORITY_VALUES = ("low", "normal", "high", "urgent")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class FollowUpTaskRow(Base):
    __tablename__ = "follow_up_tasks"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    conversation_thread_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    source_finding_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    assigned_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    due_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_finding_id"],
            ["conversation_findings.tenant_id", "conversation_findings.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "assigned_membership_id"],
            ["memberships.tenant_id", "memberships.id"],
        ),
        CheckConstraint(f"status IN ({_quoted(_STATUS_VALUES)})", name="status"),
        CheckConstraint(f"priority IN ({_quoted(_PRIORITY_VALUES)})", name="priority"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_follow_up_tasks_tenant_status_due_at", "tenant_id", "status", "due_at"),
        Index("ix_follow_up_tasks_tenant_thread_id", "tenant_id", "conversation_thread_id"),
        Index(
            "ix_follow_up_tasks_tenant_assignee_status",
            "tenant_id",
            "assigned_membership_id",
            "status",
        ),
        Index("ix_follow_up_tasks_tenant_updated_at_id", "tenant_id", "updated_at", "id"),
    )
