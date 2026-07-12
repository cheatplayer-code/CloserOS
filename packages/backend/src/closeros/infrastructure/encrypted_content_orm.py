"""SQLAlchemy ORM models for encrypted content persistence."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import BYTEA, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.domain.encrypted_content import (
    CONTENT_AAD_VERSION,
    CSV_IMPORT_MAX_PLAINTEXT_BYTES,
    GCM_NONCE_SIZE_BYTES,
    MAX_KEY_VERSION_LENGTH,
    PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES,
    RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES,
    ContentEncoding,
    EncryptedContentKind,
    EncryptionAlgorithm,
)
from closeros.infrastructure.orm_base import Base

_KIND_VALUES = tuple(kind.value for kind in EncryptedContentKind)
_ENCODING_VALUES = tuple(encoding.value for encoding in ContentEncoding)
_ALGORITHM_VALUES = tuple(algorithm.value for algorithm in EncryptionAlgorithm)


def _quoted_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class EncryptedContentRow(Base):
    __tablename__ = "encrypted_contents"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    encoding: Mapped[str] = mapped_column(String(16), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    content_nonce: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    wrapped_data_key: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    key_wrap_nonce: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    key_version: Mapped[str] = mapped_column(String(MAX_KEY_VERSION_LENGTH), nullable=False)
    aad_version: Mapped[int] = mapped_column(Integer, nullable=False)
    plaintext_byte_length: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(
            f"kind IN ({_quoted_values(_KIND_VALUES)})",
            name="kind",
        ),
        CheckConstraint(
            f"encoding IN ({_quoted_values(_ENCODING_VALUES)})",
            name="encoding",
        ),
        CheckConstraint(
            f"algorithm IN ({_quoted_values(_ALGORITHM_VALUES)})",
            name="algorithm",
        ),
        CheckConstraint(
            "octet_length(ciphertext) >= 1",
            name="ciphertext_not_empty",
        ),
        CheckConstraint(
            f"octet_length(content_nonce) = {GCM_NONCE_SIZE_BYTES}",
            name="content_nonce_length",
        ),
        CheckConstraint(
            "octet_length(wrapped_data_key) >= 1",
            name="wrapped_data_key_not_empty",
        ),
        CheckConstraint(
            f"octet_length(key_wrap_nonce) = {GCM_NONCE_SIZE_BYTES}",
            name="key_wrap_nonce_length",
        ),
        CheckConstraint(
            "plaintext_byte_length >= 1",
            name="plaintext_byte_length_positive",
        ),
        CheckConstraint(
            f"(kind = '{EncryptedContentKind.PROVIDER_PAYLOAD.value}' "
            f"AND plaintext_byte_length <= {PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES}) OR "
            f"(kind = '{EncryptedContentKind.CSV_IMPORT.value}' "
            f"AND plaintext_byte_length <= {CSV_IMPORT_MAX_PLAINTEXT_BYTES}) OR "
            f"(kind NOT IN ('{EncryptedContentKind.PROVIDER_PAYLOAD.value}', "
            f"'{EncryptedContentKind.CSV_IMPORT.value}') "
            f"AND plaintext_byte_length <= {RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES})",
            name="plaintext_byte_length_kind_limit",
        ),
        CheckConstraint(
            f"aad_version >= {CONTENT_AAD_VERSION}",
            name="aad_version",
        ),
        CheckConstraint(
            f"key_version ~ '^[A-Za-z0-9][A-Za-z0-9_-]{{0,{MAX_KEY_VERSION_LENGTH - 1}}}$'",
            name="key_version_format",
        ),
        CheckConstraint(
            "expires_at >= created_at",
            name="expires_at_not_before_created_at",
        ),
        Index(
            "ix_encrypted_contents_tenant_id_kind_created_at",
            "tenant_id",
            "kind",
            "created_at",
        ),
        Index(
            "ix_encrypted_contents_tenant_id_expires_at",
            "tenant_id",
            "expires_at",
        ),
        Index(
            "ix_encrypted_contents_tenant_id_key_version",
            "tenant_id",
            "key_version",
        ),
        Index(
            "ix_encrypted_contents_expires_at_tenant_id",
            "expires_at",
            "tenant_id",
        ),
    )
