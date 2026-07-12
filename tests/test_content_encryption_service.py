"""Unit and integration tests for ContentEncryptionService."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from closeros.application.audit_persistence import AuditAppendRequiredError, AuditQueryFilter
from closeros.application.audit_recording import AuditContext
from closeros.application.content_encryption_service import (
    ContentAccessDeniedError,
    ContentEncryptionUnavailableError,
    ContentTenantUnavailableError,
)
from closeros.application.persistence_errors import TenantMismatchError
from closeros.domain.audit import AuditAction, AuditActorType
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    EncryptedContentKind,
)
from closeros.domain.identity import TenantStatus

from tests.encryption_support import (
    AUDIT_EVENT_ID,
    CONTENT_B_ID,
    CONTENT_ID,
    NOW,
    SERVICE_ID,
    SYNTHETIC_PLAINTEXT_UTF8,
    build_content_encryption_service,
    build_test_key_provider,
)
from tests.tenant_persistence_support import TENANT_A_ID, TENANT_B_ID, synthetic_tenant

pytestmark = pytest.mark.hi_persistence

CORRELATION_ID = UUID("00000000-0000-0000-0000-000000000999")


def _audit_context() -> AuditContext:
    return AuditContext(correlation_id=CORRELATION_ID)


async def _seed_active_tenant(integrated_uow_factory: Any) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant())
        await uow.commit()


def test_encrypt_and_persist_round_trip(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_active_tenant(integrated_uow_factory)
        service = build_content_encryption_service(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            encrypted = await service.encrypt_and_persist(
                uow,
                content_id=CONTENT_ID,
                tenant_id=TENANT_A_ID,
                kind=EncryptedContentKind.RAW_MESSAGE,
                encoding=ContentEncoding.UTF8,
                plaintext=SYNTHETIC_PLAINTEXT_UTF8,
                created_at=NOW,
            )
            await uow.commit()
        assert encrypted.key_version == build_test_key_provider().active_key_version

    asyncio.run(exercise())


def test_encrypt_and_persist_rejects_inactive_tenant(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = integrated_uow_factory()
        async with uow:
            await uow.tenants.add(
                synthetic_tenant(status=TenantStatus.SUSPENDED),
            )
            await uow.commit()
        service = build_content_encryption_service(integrated_uow_factory)
        write = integrated_uow_factory()
        async with write:
            with pytest.raises(ContentTenantUnavailableError):
                await service.encrypt_and_persist(
                    write,
                    content_id=CONTENT_ID,
                    tenant_id=TENANT_A_ID,
                    kind=EncryptedContentKind.RAW_MESSAGE,
                    encoding=ContentEncoding.UTF8,
                    plaintext=SYNTHETIC_PLAINTEXT_UTF8,
                    created_at=NOW,
                )

    asyncio.run(exercise())


def test_load_and_decrypt_with_audit(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_active_tenant(integrated_uow_factory)
        service = build_content_encryption_service(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            await service.encrypt_and_persist(
                uow,
                content_id=CONTENT_ID,
                tenant_id=TENANT_A_ID,
                kind=EncryptedContentKind.RAW_MESSAGE,
                encoding=ContentEncoding.UTF8,
                plaintext=SYNTHETIC_PLAINTEXT_UTF8,
                created_at=NOW,
            )
            await uow.commit()
        decrypted = await service.load_and_decrypt(
            tenant_id=TENANT_A_ID,
            content_id=CONTENT_ID,
            purpose=ContentAccessPurpose.REDACTION,
            occurred_at=NOW,
            audit_context=_audit_context(),
            actor_type=AuditActorType.SERVICE,
            actor_id=SERVICE_ID,
            audit_event_id=AUDIT_EVENT_ID,
        )
        assert decrypted.as_utf8_text() == SYNTHETIC_PLAINTEXT_UTF8.decode("utf-8")
        audit_uow = integrated_uow_factory()
        async with audit_uow:
            page = await audit_uow.audit_events.query_page(
                query_filter=AuditQueryFilter(tenant_id=TENANT_A_ID),
                cursor=None,
                page_size=10,
            )
        assert any(
            event.action is AuditAction.ENCRYPTED_CONTENT_ACCESSED
            and event.target.target_id == CONTENT_ID
            for event in page.events
        )

    asyncio.run(exercise())


def test_load_and_decrypt_cross_tenant_returns_unavailable(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_active_tenant(integrated_uow_factory)
        service = build_content_encryption_service(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            await service.encrypt_and_persist(
                uow,
                content_id=CONTENT_ID,
                tenant_id=TENANT_A_ID,
                kind=EncryptedContentKind.RAW_MESSAGE,
                encoding=ContentEncoding.UTF8,
                plaintext=SYNTHETIC_PLAINTEXT_UTF8,
                created_at=NOW,
            )
            await uow.commit()
        with pytest.raises(TenantMismatchError, match="tenant scope mismatch"):
            await service.load_and_decrypt(
                tenant_id=TENANT_B_ID,
                content_id=CONTENT_ID,
                purpose=ContentAccessPurpose.REDACTION,
                occurred_at=NOW,
                audit_context=_audit_context(),
                actor_type=AuditActorType.SERVICE,
                actor_id=SERVICE_ID,
                audit_event_id=uuid4(),
            )

    asyncio.run(exercise())


def test_load_and_decrypt_rejects_disallowed_purpose(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_active_tenant(integrated_uow_factory)
        service = build_content_encryption_service(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            await service.encrypt_and_persist(
                uow,
                content_id=CONTENT_ID,
                tenant_id=TENANT_A_ID,
                kind=EncryptedContentKind.SANITIZED_MESSAGE,
                encoding=ContentEncoding.UTF8,
                plaintext=SYNTHETIC_PLAINTEXT_UTF8,
                created_at=NOW,
            )
            await uow.commit()
        with pytest.raises(ContentAccessDeniedError):
            await service.load_and_decrypt(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_ID,
                purpose=ContentAccessPurpose.WEBHOOK_NORMALIZATION,
                occurred_at=NOW,
                audit_context=_audit_context(),
                actor_type=AuditActorType.SERVICE,
                actor_id=SERVICE_ID,
                audit_event_id=uuid4(),
            )

    asyncio.run(exercise())


def test_audit_failure_blocks_decrypt_return(integrated_uow_factory: Any) -> None:
    from unittest.mock import AsyncMock, patch

    async def exercise() -> None:
        await _seed_active_tenant(integrated_uow_factory)
        service = build_content_encryption_service(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            await service.encrypt_and_persist(
                uow,
                content_id=CONTENT_ID,
                tenant_id=TENANT_A_ID,
                kind=EncryptedContentKind.RAW_MESSAGE,
                encoding=ContentEncoding.UTF8,
                plaintext=SYNTHETIC_PLAINTEXT_UTF8,
                created_at=NOW,
            )
            await uow.commit()

        with (
            patch(
                "closeros.application.content_encryption_service.append_required_audit_event",
                AsyncMock(
                    side_effect=AuditAppendRequiredError("required audit append failed"),
                ),
            ),
            pytest.raises(AuditAppendRequiredError),
        ):
            await service.load_and_decrypt(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_ID,
                purpose=ContentAccessPurpose.REDACTION,
                occurred_at=NOW,
                audit_context=_audit_context(),
                actor_type=AuditActorType.SERVICE,
                actor_id=SERVICE_ID,
                audit_event_id=uuid4(),
            )

        audit_uow = integrated_uow_factory()
        async with audit_uow:
            page = await audit_uow.audit_events.query_page(
                query_filter=AuditQueryFilter(
                    tenant_id=TENANT_A_ID,
                    target_id=CONTENT_ID,
                    action=AuditAction.ENCRYPTED_CONTENT_ACCESSED,
                ),
                cursor=None,
                page_size=10,
            )
        assert page.events == ()

    asyncio.run(exercise())


def test_rewrap_content_key(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_active_tenant(integrated_uow_factory)
        service = build_content_encryption_service(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            await service.encrypt_and_persist(
                uow,
                content_id=CONTENT_ID,
                tenant_id=TENANT_A_ID,
                kind=EncryptedContentKind.RAW_MESSAGE,
                encoding=ContentEncoding.UTF8,
                plaintext=SYNTHETIC_PLAINTEXT_UTF8,
                created_at=NOW,
            )
            await uow.commit()
        rewrap_uow = integrated_uow_factory()
        async with rewrap_uow:
            updated = await service.rewrap_content_key(
                rewrap_uow,
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_ID,
                occurred_at=NOW,
                audit_context=_audit_context(),
                actor_type=AuditActorType.SERVICE,
                actor_id=SERVICE_ID,
                audit_event_id=uuid4(),
            )
            await rewrap_uow.commit()
        assert updated.key_version == build_test_key_provider().active_key_version

    asyncio.run(exercise())


def test_rewrap_missing_content_raises_unavailable(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_active_tenant(integrated_uow_factory)
        service = build_content_encryption_service(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            with pytest.raises(ContentEncryptionUnavailableError):
                await service.rewrap_content_key(
                    uow,
                    tenant_id=TENANT_A_ID,
                    content_id=CONTENT_B_ID,
                    occurred_at=NOW,
                    audit_context=_audit_context(),
                    actor_type=AuditActorType.SERVICE,
                    actor_id=SERVICE_ID,
                    audit_event_id=uuid4(),
                )

    asyncio.run(exercise())
