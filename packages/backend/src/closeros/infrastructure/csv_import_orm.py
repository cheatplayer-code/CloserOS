"""SQLAlchemy ORM models for controlled CSV import persistence."""

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
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from closeros.domain.csv_import import (
    CsvDelimiter,
    CsvImportErrorCode,
    CsvImportStatus,
    CsvSourceEncoding,
)
from closeros.infrastructure.orm_base import Base

_STATUS_VALUES = tuple(status.value for status in CsvImportStatus)
_DELIMITER_VALUES = tuple(delimiter.value for delimiter in CsvDelimiter)
_ENCODING_VALUES = tuple(encoding.value for encoding in CsvSourceEncoding)
_ERROR_CODE_VALUES = tuple(code.value for code in CsvImportErrorCode)


def _quoted_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class CsvImportBatchRow(Base):
    __tablename__ = "csv_import_batches"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    channel_connection_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=False,
    )
    source_content_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    creator_user_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    delimiter: Mapped[str] = mapped_column(String(16), nullable=False)
    source_encoding: Mapped[str] = mapped_column(String(16), nullable=False)
    lawful_source_confirmed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    mapping: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    next_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(
            f"status IN ({_quoted_values(_STATUS_VALUES)})",
            name="status",
        ),
        CheckConstraint(
            f"delimiter IN ({_quoted_values(_DELIMITER_VALUES)})",
            name="delimiter",
        ),
        CheckConstraint(
            f"source_encoding IN ({_quoted_values(_ENCODING_VALUES)})",
            name="source_encoding",
        ),
        CheckConstraint("total_rows >= 0", name="total_rows_non_negative"),
        CheckConstraint("next_row_number >= 1", name="next_row_number_positive"),
        CheckConstraint("succeeded_count >= 0", name="succeeded_count_non_negative"),
        CheckConstraint("failed_count >= 0", name="failed_count_non_negative"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("expires_at >= created_at", name="expires_at_not_before_created_at"),
        ForeignKeyConstraint(
            ["tenant_id", "channel_connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
        ),
        Index(
            "ix_csv_import_batches_tenant_id_status_created_at", "tenant_id", "status", "created_at"
        ),
        Index(
            "uq_csv_import_batches_tenant_id_idempotency_key",
            "tenant_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )


class CsvImportRowErrorRow(Base):
    __tablename__ = "csv_import_row_errors"

    import_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    row_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("row_number >= 1", name="row_number_positive"),
        CheckConstraint(
            f"error_code IN ({_quoted_values(_ERROR_CODE_VALUES)})",
            name="error_code",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "import_id"],
            ["csv_import_batches.tenant_id", "csv_import_batches.id"],
            ondelete="CASCADE",
        ),
        Index("ix_csv_import_row_errors_tenant_id_import_id", "tenant_id", "import_id"),
    )
