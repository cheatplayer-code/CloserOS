"""Mappers between encrypted-content domain entities and SQLAlchemy rows."""

from __future__ import annotations

from closeros.domain.encrypted_content import (
    ContentEncoding,
    EncryptedContent,
    EncryptedContentKind,
    EncryptionAlgorithm,
    WrappedDataKey,
)
from closeros.infrastructure.encrypted_content_orm import EncryptedContentRow


def encrypted_content_to_row(content: EncryptedContent) -> EncryptedContentRow:
    return EncryptedContentRow(
        id=content.id,
        tenant_id=content.tenant_id,
        kind=content.kind.value,
        encoding=content.encoding.value,
        ciphertext=content.ciphertext,
        content_nonce=content.content_nonce,
        wrapped_data_key=content.wrapped_data_key,
        key_wrap_nonce=content.key_wrap_nonce,
        algorithm=content.algorithm.value,
        key_version=content.key_version,
        aad_version=content.aad_version,
        plaintext_byte_length=content.plaintext_byte_length,
        created_at=content.created_at,
        expires_at=content.expires_at,
    )


def encrypted_content_to_domain(row: EncryptedContentRow) -> EncryptedContent:
    return EncryptedContent(
        id=row.id,
        tenant_id=row.tenant_id,
        kind=EncryptedContentKind(row.kind),
        encoding=ContentEncoding(row.encoding),
        ciphertext=row.ciphertext,
        content_nonce=row.content_nonce,
        wrapped_data_key=row.wrapped_data_key,
        key_wrap_nonce=row.key_wrap_nonce,
        algorithm=EncryptionAlgorithm(row.algorithm),
        key_version=row.key_version,
        aad_version=row.aad_version,
        plaintext_byte_length=row.plaintext_byte_length,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


def apply_wrapped_data_key(row: EncryptedContentRow, wrapped_data_key: WrappedDataKey) -> None:
    row.wrapped_data_key = wrapped_data_key.wrapped_data_key
    row.key_wrap_nonce = wrapped_data_key.key_wrap_nonce
    row.key_version = wrapped_data_key.key_version
