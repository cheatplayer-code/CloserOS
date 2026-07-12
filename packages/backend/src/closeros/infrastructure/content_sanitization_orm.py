"""SQLAlchemy ORM models for content sanitization persistence."""

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

from closeros.domain.privacy_redaction import (
    AnalysisEligibility,
    SanitizationFailureCode,
    SanitizationStatus,
    SensitiveDataCategory,
)
from closeros.infrastructure.orm_base import Base

_STATUS_VALUES = tuple(status.value for status in SanitizationStatus)
_ELIGIBILITY_VALUES = tuple(value.value for value in AnalysisEligibility)
_FAILURE_CODE_VALUES = tuple(code.value for code in SanitizationFailureCode)
_CATEGORY_VALUES = tuple(category.value for category in SensitiveDataCategory)
_RESOURCE_TYPE_VALUES = ("message", "message_edit_event")


def _quoted_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class ContentSanitizationRow(Base):
    __tablename__ = "content_sanitizations"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    source_content_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    sanitized_content_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    source_resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_resource_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    detector_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    analysis_eligibility: Mapped[str] = mapped_column(String(16), nullable=False)
    total_finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "source_content_id",
            "policy_version",
            name="uq_content_sanitizations_tenant_source_policy",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            name="fk_content_sanitizations_source_content",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sanitized_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            name="fk_content_sanitizations_sanitized_content",
        ),
        CheckConstraint(
            f"source_resource_type IN ({_quoted_values(_RESOURCE_TYPE_VALUES)})",
            name="source_resource_type",
        ),
        CheckConstraint(
            f"status IN ({_quoted_values(_STATUS_VALUES)})",
            name="status",
        ),
        CheckConstraint(
            f"analysis_eligibility IN ({_quoted_values(_ELIGIBILITY_VALUES)})",
            name="analysis_eligibility",
        ),
        CheckConstraint(
            f"failure_code IS NULL OR failure_code IN ({_quoted_values(_FAILURE_CODE_VALUES)})",
            name="failure_code",
        ),
        CheckConstraint("total_finding_count >= 0", name="total_finding_count_non_negative"),
        CheckConstraint(
            "critical_finding_count >= 0 AND critical_finding_count <= total_finding_count",
            name="critical_finding_count_bounds",
        ),
        CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR status != 'completed'",
            name="completed_at_required_for_completed",
        ),
        Index(
            "ix_content_sanitizations_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_content_sanitizations_tenant_source_content",
            "tenant_id",
            "source_content_id",
        ),
    )


class ContentSanitizationCategoryCountRow(Base):
    __tablename__ = "content_sanitization_category_counts"

    sanitization_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "sanitization_id"],
            ["content_sanitizations.tenant_id", "content_sanitizations.id"],
            name="fk_content_sanitization_category_counts_sanitization",
        ),
        CheckConstraint(
            f"category IN ({_quoted_values(_CATEGORY_VALUES)})",
            name="category",
        ),
        CheckConstraint("count >= 1", name="count_positive"),
        Index(
            "ix_content_sanitization_category_counts_tenant_sanitization",
            "tenant_id",
            "sanitization_id",
        ),
    )
