"""Deterministic encryption test helpers and synthetic StaticKeyProvider keys.

All key material here is synthetic test data derived from deterministic byte
patterns (for example ``bytes(range(32))``). It is NOT production secrets and
must never be treated as committed credentials.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.encryption_ports import RetentionExpiryCalculator
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.domain.encrypted_content import (
    GCM_NONCE_SIZE_BYTES,
)
from closeros.infrastructure.aes_gcm_encryption import AesGcmContentCryptography
from closeros.infrastructure.remote_kms_key_provider import RemoteKmsKeyProvider
from closeros.infrastructure.secure_random import OsSecureRandom
from closeros.infrastructure.static_key_provider import StaticKeyProvider

# Synthetic 32-byte KEK material from documented byte-range patterns only.
SYNTHETIC_KEK_V1 = bytes(range(32))
SYNTHETIC_KEK_V2 = bytes((index + 17) % 256 for index in range(32))

TEST_KEY_VERSION_V1 = "test-kek-v1"
TEST_KEY_VERSION_V2 = "test-kek-v2"

CONTENT_ID = UUID("00000000-0000-0000-0000-00000000b001")
CONTENT_B_ID = UUID("00000000-0000-0000-0000-00000000b002")
OUTBOX_JOB_ID = UUID("00000000-0000-0000-0000-00000000c001")
OUTBOX_JOB_B_ID = UUID("00000000-0000-0000-0000-00000000c002")
AUDIT_EVENT_ID = UUID("00000000-0000-0000-0000-00000000d001")
SERVICE_ID = UUID("00000000-0000-0000-0000-00000000e001")

NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=30)

SYNTHETIC_PLAINTEXT_UTF8 = b"synthetic message body for HI block tests"
SYNTHETIC_PLAINTEXT_JSON = b'{"synthetic": true, "channel": "test"}'
SYNTHETIC_PLAINTEXT_BINARY = bytes(range(64))


def build_test_keys_by_version() -> dict[str, bytes]:
    return {
        TEST_KEY_VERSION_V1: SYNTHETIC_KEK_V1,
        TEST_KEY_VERSION_V2: SYNTHETIC_KEK_V2,
    }


def build_test_key_provider(*, active_version: str = TEST_KEY_VERSION_V1) -> StaticKeyProvider:
    return StaticKeyProvider(
        keys_by_version=build_test_keys_by_version(),
        active_version=active_version,
    )


def build_production_test_key_provider() -> RemoteKmsKeyProvider:
    """Non-static key provider accepted by production composition guards."""
    return RemoteKmsKeyProvider(
        base_url="https://kms.example",
        api_token_reference="env:KMS_TOKEN",
        active_key_version="kek-v1",
        key_versions=("kek-v1",),
    )


class DeterministicSecureRandom:
    """Deterministic SecureRandom for reproducible AES-GCM unit tests."""

    __slots__ = ("_iterator",)

    def __init__(self, *, seed_bytes: bytes | None = None) -> None:
        base = seed_bytes or bytes((index * 7 + 3) % 256 for index in range(256))
        values = [
            base[offset : offset + GCM_NONCE_SIZE_BYTES]
            for offset in range(0, len(base) - GCM_NONCE_SIZE_BYTES, GCM_NONCE_SIZE_BYTES)
        ]
        if not values:
            values = [bytes(GCM_NONCE_SIZE_BYTES)]
        self._iterator = itertools.cycle(values)

    def generate_bytes(self, *, size: int) -> bytes:
        if size <= 0:
            raise ValueError("size must be greater than zero")
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            chunk = next(self._iterator)
            if len(chunk) >= remaining:
                chunks.append(chunk[:remaining])
                remaining = 0
            else:
                chunks.append(chunk)
                remaining -= len(chunk)
        return b"".join(chunks)


def build_test_cryptography(
    *,
    key_provider: StaticKeyProvider | None = None,
    secure_random: DeterministicSecureRandom | OsSecureRandom | None = None,
) -> AesGcmContentCryptography:
    return AesGcmContentCryptography(
        key_provider=key_provider or build_test_key_provider(),
        secure_random=secure_random or DeterministicSecureRandom(),
    )


def build_content_encryption_service(
    uow_factory: Callable[[], IntegratedUnitOfWork],
    *,
    key_provider: StaticKeyProvider | None = None,
    secure_random: DeterministicSecureRandom | OsSecureRandom | None = None,
) -> ContentEncryptionService:
    return ContentEncryptionService(
        data_key_cryptography=build_test_cryptography(
            key_provider=key_provider,
            secure_random=secure_random,
        ),
        retention_expiry_calculator=RetentionExpiryCalculator(),
        uow_factory=uow_factory,
    )


async def seed_canonical_encrypted_content_stubs(
    integrated_uow_factory: Callable[[], IntegratedUnitOfWork],
    *,
    tenant_id: UUID,
    content_ids: tuple[UUID, ...],
) -> None:
    """Persist encrypted-content rows referenced by canonical repository tests."""
    from closeros.domain.encrypted_content import ContentEncoding, EncryptedContentKind

    crypto = build_test_cryptography()
    uow = integrated_uow_factory()
    async with uow:
        for content_id in content_ids:
            encrypted = crypto.encrypt_plaintext(
                content_id=content_id,
                tenant_id=tenant_id,
                kind=EncryptedContentKind.RAW_MESSAGE,
                encoding=ContentEncoding.UTF8,
                plaintext=SYNTHETIC_PLAINTEXT_UTF8,
                created_at=NOW,
                expires_at=LATER,
            )
            await uow.encrypted_contents.add(encrypted)
        await uow.commit()
