"""Development encryption helpers for operator scripts."""

from __future__ import annotations

import os
from collections.abc import Callable
from uuid import UUID

from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.encryption_ports import RetentionExpiryCalculator
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.infrastructure.aes_gcm_encryption import AesGcmContentCryptography
from closeros.infrastructure.secure_random import OsSecureRandom
from closeros.infrastructure.static_key_provider import StaticKeyProvider

_DEV_KEK_V1 = bytes(range(32))
_DEV_KEY_VERSION = "dev-kek-v1"
_DEFAULT_SERVICE_ID = UUID("00000000-0000-0000-0000-00000000e001")


def development_key_provider() -> StaticKeyProvider:
    return StaticKeyProvider(
        keys_by_version={_DEV_KEY_VERSION: _DEV_KEK_V1},
        active_version=_DEV_KEY_VERSION,
    )


def build_ops_content_encryption_service(
    uow_factory: Callable[[], IntegratedUnitOfWork],
) -> ContentEncryptionService:
    return ContentEncryptionService(
        data_key_cryptography=AesGcmContentCryptography(
            key_provider=development_key_provider(),
            secure_random=OsSecureRandom(),
        ),
        retention_expiry_calculator=RetentionExpiryCalculator(),
        uow_factory=uow_factory,
    )


def ingestion_service_id_from_env() -> UUID:
    raw = os.environ.get("INGESTION_SERVICE_ID", "").strip()
    if raw:
        return UUID(raw)
    return _DEFAULT_SERVICE_ID
