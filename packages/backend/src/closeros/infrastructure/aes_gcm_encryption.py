"""AES-256-GCM content encryption adapter.

Implements the application :class:`DataKeyCryptography` port using maintained
``cryptography`` primitives. No custom cryptography is implemented here.

The adapter never places plaintext, ciphertext, wrapped keys, or nonces in its
``repr`` or in any exception message.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from closeros.application.encryption_ports import KeyProvider, SecureRandom
from closeros.domain.encrypted_content import (
    CONTENT_AAD_VERSION,
    DATA_ENCRYPTION_KEY_SIZE_BYTES,
    GCM_NONCE_SIZE_BYTES,
    ContentEncoding,
    ContentUnavailableError,
    DecryptedContent,
    EncryptedContent,
    EncryptedContentKind,
    EncryptionAlgorithm,
    WrappedDataKey,
    validate_plaintext_for_kind,
)


def build_content_aad(
    *,
    tenant_id: UUID,
    content_id: UUID,
    kind: EncryptedContentKind,
    encoding: ContentEncoding,
    aad_version: int,
) -> bytes:
    return (
        f"closeros-content-v{aad_version}|{tenant_id}|{content_id}|{kind.value}|{encoding.value}"
    ).encode()


def build_key_wrap_aad(
    *,
    tenant_id: UUID,
    content_id: UUID,
    key_version: str,
    aad_version: int,
) -> bytes:
    return (f"closeros-dek-wrap-v{aad_version}|{tenant_id}|{content_id}|{key_version}").encode()


class AesGcmContentCryptography:
    """AES-256-GCM implementation of the data-key cryptography port."""

    __slots__ = ("_key_provider", "_secure_random")

    def __init__(
        self,
        *,
        key_provider: KeyProvider,
        secure_random: SecureRandom,
    ) -> None:
        self._key_provider = key_provider
        self._secure_random = secure_random

    def __repr__(self) -> str:
        return "AesGcmContentCryptography()"

    def encrypt_plaintext(
        self,
        *,
        content_id: UUID,
        tenant_id: UUID,
        kind: EncryptedContentKind,
        encoding: ContentEncoding,
        plaintext: bytes,
        created_at: datetime,
        expires_at: datetime,
        aad_version: int = CONTENT_AAD_VERSION,
    ) -> EncryptedContent:
        validated_plaintext = validate_plaintext_for_kind(kind=kind, plaintext=plaintext)
        data_key = self._secure_random.generate_bytes(size=DATA_ENCRYPTION_KEY_SIZE_BYTES)
        content_nonce = self._secure_random.generate_bytes(size=GCM_NONCE_SIZE_BYTES)
        key_wrap_nonce = self._secure_random.generate_bytes(size=GCM_NONCE_SIZE_BYTES)

        content_associated_data = build_content_aad(
            tenant_id=tenant_id,
            content_id=content_id,
            kind=kind,
            encoding=encoding,
            aad_version=aad_version,
        )
        ciphertext = self._encrypt_with_aes_gcm(
            key_material=data_key,
            nonce=content_nonce,
            associated_data=content_associated_data,
            plaintext=validated_plaintext,
        )

        key_version = self._key_provider.active_key_version
        wrapped_data_key = self._key_provider.wrap_data_key(
            tenant_id=tenant_id,
            content_id=content_id,
            aad_version=aad_version,
            data_key=data_key,
            key_wrap_nonce=key_wrap_nonce,
            key_version=key_version,
        )

        return EncryptedContent(
            id=content_id,
            tenant_id=tenant_id,
            kind=kind,
            encoding=encoding,
            ciphertext=ciphertext,
            content_nonce=content_nonce,
            wrapped_data_key=wrapped_data_key,
            key_wrap_nonce=key_wrap_nonce,
            algorithm=EncryptionAlgorithm.AES_256_GCM,
            key_version=key_version,
            aad_version=aad_version,
            plaintext_byte_length=len(validated_plaintext),
            created_at=created_at,
            expires_at=expires_at,
        )

    def decrypt_content(self, *, encrypted: EncryptedContent) -> DecryptedContent:
        if not isinstance(encrypted, EncryptedContent):
            raise TypeError("encrypted must be an EncryptedContent")

        data_key = self._key_provider.unwrap_data_key(
            tenant_id=encrypted.tenant_id,
            content_id=encrypted.id,
            aad_version=encrypted.aad_version,
            wrapped_data_key=encrypted.wrapped_data_key,
            key_wrap_nonce=encrypted.key_wrap_nonce,
            key_version=encrypted.key_version,
        )

        content_associated_data = build_content_aad(
            tenant_id=encrypted.tenant_id,
            content_id=encrypted.id,
            kind=encrypted.kind,
            encoding=encrypted.encoding,
            aad_version=encrypted.aad_version,
        )
        plaintext = self._decrypt_with_aes_gcm(
            key_material=data_key,
            nonce=encrypted.content_nonce,
            associated_data=content_associated_data,
            ciphertext=encrypted.ciphertext,
        )

        if len(plaintext) != encrypted.plaintext_byte_length:
            raise ContentUnavailableError("encrypted content is unavailable")

        return DecryptedContent(
            kind=encrypted.kind,
            encoding=encrypted.encoding,
            plaintext_byte_length=encrypted.plaintext_byte_length,
            _plaintext=plaintext,
        )

    def rewrap_data_key(self, *, encrypted: EncryptedContent) -> WrappedDataKey:
        if not isinstance(encrypted, EncryptedContent):
            raise TypeError("encrypted must be an EncryptedContent")

        data_key = self._key_provider.unwrap_data_key(
            tenant_id=encrypted.tenant_id,
            content_id=encrypted.id,
            aad_version=encrypted.aad_version,
            wrapped_data_key=encrypted.wrapped_data_key,
            key_wrap_nonce=encrypted.key_wrap_nonce,
            key_version=encrypted.key_version,
        )

        key_wrap_nonce = self._secure_random.generate_bytes(size=GCM_NONCE_SIZE_BYTES)
        key_version = self._key_provider.active_key_version
        wrapped_data_key = self._key_provider.wrap_data_key(
            tenant_id=encrypted.tenant_id,
            content_id=encrypted.id,
            aad_version=encrypted.aad_version,
            data_key=data_key,
            key_wrap_nonce=key_wrap_nonce,
            key_version=key_version,
        )

        return WrappedDataKey(
            wrapped_data_key=wrapped_data_key,
            key_wrap_nonce=key_wrap_nonce,
            key_version=key_version,
        )

    @staticmethod
    def _encrypt_with_aes_gcm(
        *,
        key_material: bytes,
        nonce: bytes,
        associated_data: bytes,
        plaintext: bytes,
    ) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        if len(key_material) != DATA_ENCRYPTION_KEY_SIZE_BYTES:
            raise ValueError("key material must contain exactly 32 bytes")

        if len(nonce) != GCM_NONCE_SIZE_BYTES:
            raise ValueError("nonce must contain exactly 12 bytes")

        try:
            return AESGCM(key_material).encrypt(nonce, plaintext, associated_data)
        except Exception as exc:
            raise ContentUnavailableError("encrypted content is unavailable") from exc

    @staticmethod
    def _decrypt_with_aes_gcm(
        *,
        key_material: bytes,
        nonce: bytes,
        associated_data: bytes,
        ciphertext: bytes,
    ) -> bytes:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        if len(key_material) != DATA_ENCRYPTION_KEY_SIZE_BYTES:
            raise ValueError("key material must contain exactly 32 bytes")

        if len(nonce) != GCM_NONCE_SIZE_BYTES:
            raise ValueError("nonce must contain exactly 12 bytes")

        try:
            return AESGCM(key_material).decrypt(nonce, ciphertext, associated_data)
        except InvalidTag as exc:
            raise ContentUnavailableError("encrypted content is unavailable") from exc
        except Exception as exc:
            raise ContentUnavailableError("encrypted content is unavailable") from exc
