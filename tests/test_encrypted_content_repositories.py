"""PostgreSQL integration tests for encrypted-content repositories."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from closeros.application.encrypted_content_persistence import (
    DuplicateEncryptedContentError,
    EncryptedContentRecordNotFoundError,
    EncryptedContentRetentionFilter,
)
from closeros.application.persistence_errors import TenantMismatchError
from closeros.domain.encrypted_content import (
    ContentEncoding,
    EncryptedContent,
    EncryptedContentKind,
)

from tests.encryption_support import (
    CONTENT_B_ID,
    CONTENT_ID,
    LATER,
    NOW,
    SYNTHETIC_PLAINTEXT_UTF8,
    TEST_KEY_VERSION_V2,
    build_test_cryptography,
    build_test_key_provider,
)
from tests.tenant_persistence_support import TENANT_A_ID, TENANT_B_ID, synthetic_tenant

pytestmark = pytest.mark.hi_persistence


async def _seed_tenant(integrated_uow_factory: Any, *, tenant_id: UUID = TENANT_A_ID) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant(tenant_id=tenant_id))
        await uow.commit()


async def _persist_encrypted(
    integrated_uow_factory: Any,
    *,
    content_id: UUID = CONTENT_ID,
    tenant_id: UUID = TENANT_A_ID,
    seed_tenant: bool = True,
) -> EncryptedContent:
    if seed_tenant:
        await _seed_tenant(integrated_uow_factory, tenant_id=tenant_id)
    crypto = build_test_cryptography()
    encrypted = crypto.encrypt_plaintext(
        content_id=content_id,
        tenant_id=tenant_id,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext=SYNTHETIC_PLAINTEXT_UTF8,
        created_at=NOW,
        expires_at=LATER,
    )
    uow = integrated_uow_factory()
    async with uow:
        await uow.encrypted_contents.add(encrypted)
        await uow.commit()
    return encrypted


def test_encrypted_content_repository_round_trip(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        encrypted = await _persist_encrypted(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            restored = await uow.encrypted_contents.get_by_id(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_ID,
            )
        assert restored is not None
        assert restored.id == encrypted.id
        assert restored.key_version == encrypted.key_version
        assert restored.plaintext_byte_length == len(SYNTHETIC_PLAINTEXT_UTF8)

    asyncio.run(exercise())


def test_encrypted_content_repository_cross_tenant_lookup_raises(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _persist_encrypted(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            with pytest.raises(TenantMismatchError, match="tenant scope mismatch"):
                await uow.encrypted_contents.get_by_id(
                    tenant_id=TENANT_B_ID,
                    content_id=CONTENT_ID,
                )

    asyncio.run(exercise())


def test_encrypted_content_repository_rejects_duplicate(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        encrypted = await _persist_encrypted(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            with pytest.raises(DuplicateEncryptedContentError):
                await uow.encrypted_contents.add(encrypted)
                await uow.commit()
            await uow.rollback()

    asyncio.run(exercise())


def test_encrypted_content_get_for_update(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _persist_encrypted(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            locked = await uow.encrypted_contents.get_for_update(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_ID,
            )
            assert locked is not None
            assert locked.id == CONTENT_ID

    asyncio.run(exercise())


def test_encrypted_content_replace_wrapped_key(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        encrypted = await _persist_encrypted(integrated_uow_factory)
        crypto = build_test_cryptography()
        rewrapped = crypto.rewrap_data_key(encrypted=encrypted)
        uow = integrated_uow_factory()
        async with uow:
            await uow.encrypted_contents.replace_wrapped_key(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_ID,
                wrapped_data_key=rewrapped,
            )
            await uow.commit()
        lookup = integrated_uow_factory()
        async with lookup:
            updated = await lookup.encrypted_contents.get_by_id(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_ID,
            )
        assert updated is not None
        assert updated.key_version == rewrapped.key_version

    asyncio.run(exercise())


def test_encrypted_content_replace_wrapped_key_missing_record(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_tenant(integrated_uow_factory)
        crypto = build_test_cryptography()
        encrypted = crypto.encrypt_plaintext(
            content_id=CONTENT_ID,
            tenant_id=TENANT_A_ID,
            kind=EncryptedContentKind.RAW_MESSAGE,
            encoding=ContentEncoding.UTF8,
            plaintext=SYNTHETIC_PLAINTEXT_UTF8,
            created_at=NOW,
            expires_at=LATER,
        )
        rewrapped = crypto.rewrap_data_key(encrypted=encrypted)
        uow = integrated_uow_factory()
        async with uow:
            with pytest.raises(EncryptedContentRecordNotFoundError):
                await uow.encrypted_contents.replace_wrapped_key(
                    tenant_id=TENANT_A_ID,
                    content_id=CONTENT_ID,
                    wrapped_data_key=rewrapped,
                )

    asyncio.run(exercise())


def test_encrypted_content_list_by_tenant_and_kind(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _persist_encrypted(integrated_uow_factory)
        await _persist_encrypted(
            integrated_uow_factory,
            content_id=CONTENT_B_ID,
            seed_tenant=False,
        )
        uow = integrated_uow_factory()
        async with uow:
            rows = await uow.encrypted_contents.list_by_tenant_and_kind(
                tenant_id=TENANT_A_ID,
                kind=EncryptedContentKind.RAW_MESSAGE,
            )
        assert len(rows) == 2

    asyncio.run(exercise())


def test_encrypted_content_list_due_for_retention(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        encrypted = await _persist_encrypted(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            due = await uow.encrypted_contents.list_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    tenant_id=TENANT_A_ID,
                    expires_before=encrypted.expires_at + timedelta(seconds=1),
                    limit=10,
                ),
            )
        assert len(due) == 1
        assert due[0].id == CONTENT_ID

    asyncio.run(exercise())


def test_encrypted_content_list_due_for_retention_excludes_future_expiry(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _persist_encrypted(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            due = await uow.encrypted_contents.list_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    tenant_id=TENANT_A_ID,
                    expires_before=NOW,
                    limit=10,
                ),
            )
        assert due == ()

    asyncio.run(exercise())


def test_encrypted_content_replace_wrapped_key_updates_version(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        encrypted = await _persist_encrypted(integrated_uow_factory)
        provider = build_test_key_provider(active_version=TEST_KEY_VERSION_V2)
        crypto = build_test_cryptography(key_provider=provider)
        rewrapped = crypto.rewrap_data_key(encrypted=encrypted)
        uow = integrated_uow_factory()
        async with uow:
            await uow.encrypted_contents.replace_wrapped_key(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_ID,
                wrapped_data_key=rewrapped,
            )
            await uow.commit()
        lookup = integrated_uow_factory()
        async with lookup:
            updated = await lookup.encrypted_contents.get_by_id(
                tenant_id=TENANT_A_ID,
                content_id=CONTENT_ID,
            )
        assert updated is not None
        assert updated.key_version == TEST_KEY_VERSION_V2
        decrypted = crypto.decrypt_content(encrypted=updated)
        assert decrypted.as_utf8_text() == SYNTHETIC_PLAINTEXT_UTF8.decode("utf-8")

    asyncio.run(exercise())


def test_encrypted_content_repository_rejects_invalid_limit(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _persist_encrypted(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            with pytest.raises(ValueError, match="limit must be positive"):
                await uow.encrypted_contents.list_by_tenant_and_kind(
                    tenant_id=TENANT_A_ID,
                    kind=EncryptedContentKind.RAW_MESSAGE,
                    limit=0,
                )

    asyncio.run(exercise())
