"""Application-facing encryption ports and retention expiry helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from closeros.domain.encrypted_content import (
    CONTENT_AAD_VERSION,
    ContentEncoding,
    DecryptedContent,
    EncryptedContent,
    EncryptedContentKind,
    WrappedDataKey,
)
from closeros.domain.retention import RetentionPolicy


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")

    return value


def _retention_days_for_kind(
    *,
    kind: EncryptedContentKind,
    policy: RetentionPolicy,
) -> int:
    if kind is EncryptedContentKind.SANITIZED_MESSAGE:
        return policy.sanitized_message_days

    return policy.raw_message_days


def calculate_encrypted_content_expiry(
    *,
    kind: EncryptedContentKind,
    created_at: datetime,
    policy: RetentionPolicy,
) -> datetime:
    if not isinstance(kind, EncryptedContentKind):
        raise TypeError("kind must be an EncryptedContentKind")

    validated_created_at = _validate_timezone_aware_datetime(created_at, "created_at")

    if not isinstance(policy, RetentionPolicy):
        raise TypeError("policy must be a RetentionPolicy")

    retention_days = _retention_days_for_kind(kind=kind, policy=policy)
    return validated_created_at + timedelta(days=retention_days)


@dataclass(frozen=True, slots=True)
class RetentionExpiryCalculator:
    """Derives encrypted-content expiry timestamps from tenant retention policy."""

    def calculate_expires_at(
        self,
        *,
        kind: EncryptedContentKind,
        created_at: datetime,
        policy: RetentionPolicy,
    ) -> datetime:
        return calculate_encrypted_content_expiry(
            kind=kind,
            created_at=created_at,
            policy=policy,
        )


class SecureRandom(Protocol):
    """Port for cryptographically secure random-byte generation."""

    def generate_bytes(self, *, size: int) -> bytes: ...


class KeyProvider(Protocol):
    """Port for envelope key management suitable for a future KMS/HSM adapter."""

    @property
    def active_key_version(self) -> str: ...

    def list_key_versions(self) -> tuple[str, ...]: ...

    def wrap_data_key(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        aad_version: int,
        data_key: bytes,
        key_wrap_nonce: bytes,
        key_version: str | None = None,
    ) -> bytes: ...

    def unwrap_data_key(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        aad_version: int,
        wrapped_data_key: bytes,
        key_wrap_nonce: bytes,
        key_version: str,
    ) -> bytes: ...


class DataKeyCryptography(Protocol):
    """Port for per-content DEK encryption, decryption, and rewrap operations."""

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
    ) -> EncryptedContent: ...

    def decrypt_content(self, *, encrypted: EncryptedContent) -> DecryptedContent: ...

    def rewrap_data_key(self, *, encrypted: EncryptedContent) -> WrappedDataKey: ...
