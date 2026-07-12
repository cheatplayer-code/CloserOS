"""SQLAlchemy ORM models for knowledge persistence."""

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
from sqlalchemy.dialects.postgresql import BYTEA, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.infrastructure.orm_base import Base

_DOCUMENT_SOURCE_VALUES = ("upload", "import", "system_seed")
_DOCUMENT_STATUS_VALUES = ("active", "archived", "deleted")
_VERSION_STATUS_VALUES = ("draft", "approved", "indexed", "revoked", "superseded")
_CHUNK_STATUS_VALUES = ("active", "revoked")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class KnowledgeDocumentRow(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(
            f"source_type IN ({_quoted(_DOCUMENT_SOURCE_VALUES)})",
            name="source_type",
        ),
        CheckConstraint(
            f"status IN ({_quoted(_DOCUMENT_STATUS_VALUES)})",
            name="status",
        ),
        Index(
            "ix_knowledge_documents_tenant_status_updated_at", "tenant_id", "status", "updated_at"
        ),
    )


class KnowledgeDocumentVersionRow(Base):
    __tablename__ = "knowledge_document_versions"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    content_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    content_sha256_digest: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "document_id", "version_number"),
        ForeignKeyConstraint(
            ("tenant_id", "document_id"),
            ("knowledge_documents.tenant_id", "knowledge_documents.id"),
        ),
        ForeignKeyConstraint(
            ("tenant_id", "content_id"),
            ("encrypted_contents.tenant_id", "encrypted_contents.id"),
        ),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint(
            f"status IN ({_quoted(_VERSION_STATUS_VALUES)})",
            name="status",
        ),
        CheckConstraint(
            "octet_length(content_sha256_digest) = 32", name="content_sha256_digest_length"
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="effective_window"
        ),
        Index(
            "ix_knowledge_document_versions_tenant_status_effective_from",
            "tenant_id",
            "status",
            "effective_from",
        ),
        Index(
            "ix_knowledge_document_versions_tenant_document_status",
            "tenant_id",
            "document_id",
            "status",
        ),
    )


class KnowledgeChunkRow(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    content_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    chunk_sha256_digest: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "document_version_id", "position"),
        ForeignKeyConstraint(
            ("tenant_id", "document_version_id"),
            ("knowledge_document_versions.tenant_id", "knowledge_document_versions.id"),
        ),
        ForeignKeyConstraint(
            ("tenant_id", "content_id"),
            ("encrypted_contents.tenant_id", "encrypted_contents.id"),
        ),
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint(
            f"status IN ({_quoted(_CHUNK_STATUS_VALUES)})",
            name="status",
        ),
        CheckConstraint(
            "octet_length(chunk_sha256_digest) = 32", name="chunk_sha256_digest_length"
        ),
        CheckConstraint("token_count >= 0", name="token_count_non_negative"),
        Index(
            "ix_knowledge_chunks_tenant_document_version_status",
            "tenant_id",
            "document_version_id",
            "status",
        ),
        Index("ix_knowledge_chunks_tenant_chunk_sha256_digest", "tenant_id", "chunk_sha256_digest"),
    )


class KnowledgeChunkTermRow(Base):
    __tablename__ = "knowledge_chunk_terms"

    chunk_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    term_digest: Mapped[bytes] = mapped_column(BYTEA, primary_key=True)
    weight_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "chunk_id"),
            ("knowledge_chunks.tenant_id", "knowledge_chunks.id"),
            ondelete="CASCADE",
        ),
        CheckConstraint("octet_length(term_digest) = 32", name="term_digest_length"),
        CheckConstraint(
            "weight_basis_points >= 0 AND weight_basis_points <= 10000",
            name="weight_basis_points",
        ),
        Index("ix_knowledge_chunk_terms_tenant_term_digest", "tenant_id", "term_digest"),
    )
