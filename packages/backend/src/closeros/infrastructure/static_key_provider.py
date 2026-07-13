"""Development/test static key provider.

Never use in production. Production composition must inject an explicit
production-grade key-provider adapter or fail closed.
"""

from __future__ import annotations

from uuid import UUID

from closeros.domain.encrypted_content import (
    DATA_ENCRYPTION_KEY_SIZE_BYTES,
    GCM_NONCE_SIZE_BYTES,
    ContentUnavailableError,
)
from closeros.infrastructure.aes_gcm_encryption import build_key_wrap_aad


class ProductionKeyProviderRequiredError(RuntimeError):
    """Raised when production composition lacks an explicit key-provider adapter."""


class ProductionStaticKeyProviderRejectedError(RuntimeError):
    """Raised when production composition attempts to use StaticKeyProvider."""


class StaticKeyProvider:
    """Development/test AES-GCM key provider backed by in-memory 32-byte keys."""

    __slots__ = ("_active_key_version", "_keys_by_version")

    def __init__(
        self,
        *,
        keys_by_version: dict[str, bytes],
        active_version: str,
    ) -> None:
        if not isinstance(keys_by_version, dict):
            raise TypeError("keys_by_version must be a dict")

        if not keys_by_version:
            raise ValueError("keys_by_version must not be empty")

        if type(active_version) is not str or not active_version:
            raise ValueError("active_version must be a non-empty string")

        normalized_keys: dict[str, bytes] = {}

        for version, key_material in keys_by_version.items():
            if type(version) is not str or not version:
                raise ValueError("key versions must be non-empty strings")

            if type(key_material) is not bytes:
                raise TypeError("key material must be bytes")

            if len(key_material) != DATA_ENCRYPTION_KEY_SIZE_BYTES:
                raise ValueError("key material must contain exactly 32 bytes")

            normalized_keys[version] = key_material

        if active_version not in normalized_keys:
            raise ValueError("active_version must exist in keys_by_version")

        self._keys_by_version = normalized_keys
        self._active_key_version = active_version

    def __repr__(self) -> str:
        return (
            "StaticKeyProvider("
            f"versions={len(self._keys_by_version)}, "
            f"active_version={self._active_key_version!r})"
        )

    @property
    def active_key_version(self) -> str:
        return self._active_key_version

    def list_key_versions(self) -> tuple[str, ...]:
        return tuple(sorted(self._keys_by_version))

    def wrap_data_key(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        aad_version: int,
        data_key: bytes,
        key_wrap_nonce: bytes,
        key_version: str | None = None,
    ) -> bytes:
        resolved_key_version = key_version or self._active_key_version
        key_encryption_key = self._resolve_key_material(resolved_key_version)
        associated_data = build_key_wrap_aad(
            tenant_id=tenant_id,
            content_id=content_id,
            key_version=resolved_key_version,
            aad_version=aad_version,
        )
        return self._encrypt_with_aes_gcm(
            key_material=key_encryption_key,
            nonce=key_wrap_nonce,
            associated_data=associated_data,
            plaintext=data_key,
        )

    def unwrap_data_key(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        aad_version: int,
        wrapped_data_key: bytes,
        key_wrap_nonce: bytes,
        key_version: str,
    ) -> bytes:
        key_encryption_key = self._resolve_key_material(key_version)
        associated_data = build_key_wrap_aad(
            tenant_id=tenant_id,
            content_id=content_id,
            key_version=key_version,
            aad_version=aad_version,
        )
        return self._decrypt_with_aes_gcm(
            key_material=key_encryption_key,
            nonce=key_wrap_nonce,
            associated_data=associated_data,
            ciphertext=wrapped_data_key,
        )

    def _resolve_key_material(self, key_version: str) -> bytes:
        try:
            return self._keys_by_version[key_version]
        except KeyError as exc:
            raise ContentUnavailableError("content key is unavailable") from exc

    @staticmethod
    def _encrypt_with_aes_gcm(
        *,
        key_material: bytes,
        nonce: bytes,
        associated_data: bytes,
        plaintext: bytes,
    ) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        if len(nonce) != GCM_NONCE_SIZE_BYTES:
            raise ValueError("nonce must contain exactly 12 bytes")

        try:
            return AESGCM(key_material).encrypt(nonce, plaintext, associated_data)
        except Exception as exc:
            raise ContentUnavailableError("content key wrapping failed") from exc

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

        if len(nonce) != GCM_NONCE_SIZE_BYTES:
            raise ValueError("nonce must contain exactly 12 bytes")

        try:
            return AESGCM(key_material).decrypt(nonce, ciphertext, associated_data)
        except InvalidTag as exc:
            raise ContentUnavailableError("content key is unavailable") from exc
        except Exception as exc:
            raise ContentUnavailableError("content key is unavailable") from exc


def require_production_key_provider(provider: object | None) -> object:
    """Fail closed unless an explicit production key-provider adapter is injected."""
    if provider is None:
        raise ProductionKeyProviderRequiredError(
            "production requires an explicit key-provider adapter"
        )
    reject_static_key_provider_in_production(provider)
    return provider


def reject_static_key_provider_in_production(provider: object) -> None:
    """Fail closed when production composition injects StaticKeyProvider."""
    if isinstance(provider, StaticKeyProvider):
        raise ProductionStaticKeyProviderRejectedError("production must not use StaticKeyProvider")
