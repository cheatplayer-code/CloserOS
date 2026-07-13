"""PostgreSQL integration tests for atomic authentication notification issuance."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from closeros.application.atomic_authentication_notification_issuance import (
    AtomicAuthenticationNotificationIssuer,
)
from closeros.application.audit_recording import AuditContext
from closeros.application.authentication_workflows import AuthenticationWorkflowService
from closeros.domain.notification_payload import PLATFORM_NOTIFICATION_TENANT_ID_STR
from closeros.domain.outbox import OutboxJobKind
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher
from closeros.security.authentication_tokens import generate_raw_authentication_token
from sqlalchemy import text

from tests.encryption_support import build_content_encryption_service
from tests.tenant_persistence_support import synthetic_tenant

pytestmark = pytest.mark.hi_persistence

NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
PLATFORM_TENANT_ID = UUID(PLATFORM_NOTIFICATION_TENANT_ID_STR)
AUDIT_CONTEXT = AuditContext(correlation_id=uuid4())


async def _seed_platform_tenant(integrated_uow_factory: Any) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant(tenant_id=PLATFORM_TENANT_ID, name="platform"))
        await uow.commit()


def test_register_commits_token_notification_and_outbox_together(
    integrated_uow_factory: Any,
    auth_async_engine: Any,
) -> None:
    async def exercise() -> None:
        await _seed_platform_tenant(integrated_uow_factory)
        content_encryption = build_content_encryption_service(integrated_uow_factory)
        issuer = AtomicAuthenticationNotificationIssuer(
            content_encryption=content_encryption,
            uuid_factory=uuid4,
            verification_base_url="https://app.example/verify",
            reset_base_url="https://app.example/reset",
        )
        workflows = AuthenticationWorkflowService(
            uow_factory=integrated_uow_factory,
            password_hasher=Argon2idPasswordHasher(),
            notification_issuer=issuer,
        )
        user_id = uuid4()
        credential_id = uuid4()
        token_id = uuid4()
        result = await workflows.register_user(
            user_id=user_id,
            credential_id=credential_id,
            verification_token_id=token_id,
            email="atomic.test@example.test",
            plaintext_password="Synthetic-Password-1",
            registered_at=NOW,
            audit_context=AUDIT_CONTEXT,
            raw_token_factory=generate_raw_authentication_token,
        )
        assert result.delivery is None

        async with auth_async_engine.connect() as connection:
            token_count = (
                await connection.execute(
                    text(
                        "SELECT COUNT(*) FROM authentication_one_time_tokens WHERE id = :token_id"
                    ),
                    {"token_id": token_id},
                )
            ).scalar_one()
            delivery_count = (
                await connection.execute(text("SELECT COUNT(*) FROM notification_deliveries"))
            ).scalar_one()
            outbox_count = (
                await connection.execute(
                    text("SELECT COUNT(*) FROM outbox_jobs WHERE job_kind = :kind"),
                    {"kind": OutboxJobKind.NOTIFICATION_DELIVER.value},
                )
            ).scalar_one()
            encrypted_count = (
                await connection.execute(
                    text(
                        "SELECT COUNT(*) FROM encrypted_contents "
                        "WHERE kind = 'notification_payload'"
                    )
                )
            ).scalar_one()

        assert token_count == 1
        assert delivery_count == 1
        assert outbox_count == 1
        assert encrypted_count == 1

    asyncio.run(exercise())


def test_register_rolls_back_when_notification_enqueue_fails(
    integrated_uow_factory: Any,
    auth_async_engine: Any,
) -> None:
    async def exercise() -> None:
        await _seed_platform_tenant(integrated_uow_factory)
        content_encryption = build_content_encryption_service(integrated_uow_factory)

        class _RaisingIssuer:
            def __init__(self) -> None:
                self._delegate = AtomicAuthenticationNotificationIssuer(
                    content_encryption=content_encryption,
                    uuid_factory=uuid4,
                    verification_base_url="https://app.example/verify",
                    reset_base_url="https://app.example/reset",
                )

            async def enqueue_in_transaction(self, uow: Any, **kwargs: Any) -> UUID:
                raise RuntimeError("notification enqueue failed")

        issuer = _RaisingIssuer()
        workflows = AuthenticationWorkflowService(
            uow_factory=integrated_uow_factory,
            password_hasher=Argon2idPasswordHasher(),
            notification_issuer=issuer,  # type: ignore[arg-type]
        )
        user_id = uuid4()
        with pytest.raises(RuntimeError, match="notification enqueue failed"):
            await workflows.register_user(
                user_id=user_id,
                credential_id=uuid4(),
                verification_token_id=uuid4(),
                email="rollback.test@example.test",
                plaintext_password="Synthetic-Password-1",
                registered_at=NOW,
                audit_context=AUDIT_CONTEXT,
            )

        async with auth_async_engine.connect() as connection:
            user_count = (
                await connection.execute(
                    text("SELECT COUNT(*) FROM users WHERE id = :user_id"),
                    {"user_id": user_id},
                )
            ).scalar_one()
            token_count = (
                await connection.execute(
                    text("SELECT COUNT(*) FROM authentication_one_time_tokens")
                )
            ).scalar_one()
            delivery_count = (
                await connection.execute(text("SELECT COUNT(*) FROM notification_deliveries"))
            ).scalar_one()

        assert user_count == 0
        assert token_count == 0
        assert delivery_count == 0

    asyncio.run(exercise())
