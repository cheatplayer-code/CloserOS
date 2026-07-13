"""Tests for production TOTP MFA verifier."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
import hashlib
import hmac
import struct
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from closeros.domain.authentication import MfaMethod
from closeros.domain.notification_payload import PLATFORM_NOTIFICATION_TENANT_ID_STR
from closeros.infrastructure.production_runtime import (
    ProductionConfigurationError,
    build_production_shared_runtime,
)
from closeros.infrastructure.totp_mfa_verifier import (
    DatabaseTotpMfaVerifier,
    enroll_totp_secret_for_tests,
)

from tests.encryption_support import SERVICE_ID, build_content_encryption_service
from tests.tenant_persistence_support import synthetic_tenant

pytestmark = pytest.mark.hi_persistence

NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
PLATFORM_TENANT_ID = UUID(PLATFORM_NOTIFICATION_TENANT_ID_STR)
SECRET_BYTES = b"synthetic-totp-secret-16b"


def _totp_for_now(*, secret: bytes) -> str:
    timestep = int(datetime.now(tz=UTC).timestamp()) // 30
    counter = struct.pack(">Q", timestep)
    digest = hmac.new(secret, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % 1_000_000).zfill(6)


async def _seed_platform_tenant(integrated_uow_factory: Any) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant(tenant_id=PLATFORM_TENANT_ID, name="platform-mfa"))
        await uow.commit()


def test_database_totp_verifier_rejects_arbitrary_code(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_tenant(integrated_uow_factory)
        content_encryption = build_content_encryption_service(integrated_uow_factory)
        user_id = uuid4()
        await enroll_totp_secret_for_tests(
            uow_factory=integrated_uow_factory,
            content_encryption=content_encryption,
            user_id=user_id,
            secret=SECRET_BYTES,
            occurred_at=NOW,
            uuid_factory=uuid4,
        )
        verifier = DatabaseTotpMfaVerifier(
            uow_factory=integrated_uow_factory,
            content_encryption=content_encryption,
            service_actor_id=SERVICE_ID,
            uuid_factory=uuid4,
        )
        accepted = await verifier.verify_mfa(
            user_id=user_id,
            method=MfaMethod.TOTP,
            response={"code": "000000"},
        )
        assert accepted is False
        assert "000000" not in repr(verifier)

    asyncio.run(exercise())


def test_database_totp_verifier_accepts_valid_code(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_platform_tenant(integrated_uow_factory)
        content_encryption = build_content_encryption_service(integrated_uow_factory)
        user_id = uuid4()
        await enroll_totp_secret_for_tests(
            uow_factory=integrated_uow_factory,
            content_encryption=content_encryption,
            user_id=user_id,
            secret=SECRET_BYTES,
            occurred_at=NOW,
            uuid_factory=uuid4,
        )
        verifier = DatabaseTotpMfaVerifier(
            uow_factory=integrated_uow_factory,
            content_encryption=content_encryption,
            service_actor_id=SERVICE_ID,
            uuid_factory=uuid4,
        )
        code = _totp_for_now(secret=SECRET_BYTES)
        assert await verifier.verify_mfa(
            user_id=user_id,
            method=MfaMethod.TOTP,
            response={"code": code},
        )
        replay = await verifier.verify_mfa(
            user_id=user_id,
            method=MfaMethod.TOTP,
            response={"code": code},
        )
        assert replay is False

    asyncio.run(exercise())


def test_production_shared_runtime_requires_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("KMS_BASE_URL", "https://kms.example")
    monkeypatch.setenv("KMS_API_TOKEN_REF", "env:KMS_TOKEN")
    monkeypatch.setenv("KMS_ACTIVE_KEY_VERSION", "kek-v1")
    monkeypatch.setenv("KMS_KEY_VERSIONS", "kek-v1")
    with pytest.raises(ProductionConfigurationError, match="REDIS_URL"):
        from tests.database_url_support import placeholder_database_url

        build_production_shared_runtime(
            database_url=placeholder_database_url(),
            ingestion_service_id=SERVICE_ID,
        )
