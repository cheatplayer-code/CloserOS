"""Integration tests for tenant context resolution."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from closeros.application.tenant_context import (
    TenantContextResolver,
    TenantContextUnavailableError,
    TenantListingService,
)
from closeros.domain.access import TENANT_ACCESS_DENIED_MESSAGE, TenantAccessDeniedError
from closeros.domain.identity import MembershipStatus, TenantStatus, UserStatus
from closeros.domain.user import User
from closeros.security.authentication_tokens import (
    RawAuthenticationToken,
    hash_authentication_token,
)

from tests.auth_api_support import TOKEN_ENTROPY_A, deterministic_token_string
from tests.auth_persistence_support import (
    LATER,
    NOW,
    synthetic_session,
    synthetic_user,
)
from tests.tenant_persistence_support import (
    MEMBERSHIP_A_ID,
    TENANT_A_ID,
    TENANT_B_ID,
    USER_ID,
    synthetic_membership,
    synthetic_tenant,
)

pytestmark = pytest.mark.platform_persistence

CORRELATION_ID = UUID("00000000-0000-0000-0000-000000000999")
RAW_TOKEN = RawAuthenticationToken(deterministic_token_string(TOKEN_ENTROPY_A))
SESSION_TOKEN_HASH = hash_authentication_token(RAW_TOKEN)


async def _seed_authenticated_membership(platform_uow_factory: Any) -> None:
    uow = platform_uow_factory()
    async with uow:
        await uow.users.add(synthetic_user())
        await uow.tenants.add(synthetic_tenant())
        await uow.memberships.add(synthetic_membership())
        await uow.sessions.add(
            synthetic_session(
                token_hash=SESSION_TOKEN_HASH,
            )
        )
        await uow.commit()


def test_tenant_context_resolver_success(platform_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_authenticated_membership(platform_uow_factory)
        resolver = TenantContextResolver(uow_factory=platform_uow_factory)

        context = await resolver.resolve(
            raw_token=RAW_TOKEN,
            tenant_id=TENANT_A_ID,
            correlation_id=CORRELATION_ID,
            now=NOW,
            touch_session=False,
        )

        assert context.tenant.id == TENANT_A_ID
        assert context.user.id == USER_ID
        assert context.membership.id == MEMBERSHIP_A_ID
        assert context.correlation_id == CORRELATION_ID

    asyncio.run(exercise())


def test_tenant_context_resolver_denies_unknown_tenant(platform_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_authenticated_membership(platform_uow_factory)
        resolver = TenantContextResolver(uow_factory=platform_uow_factory)

        with pytest.raises(TenantAccessDeniedError, match=TENANT_ACCESS_DENIED_MESSAGE):
            await resolver.resolve(
                raw_token=RAW_TOKEN,
                tenant_id=TENANT_B_ID,
                correlation_id=CORRELATION_ID,
                now=NOW,
                touch_session=False,
            )

    asyncio.run(exercise())


def test_tenant_context_resolver_denies_missing_membership(platform_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = platform_uow_factory()
        async with uow:
            await uow.users.add(synthetic_user())
            await uow.tenants.add(synthetic_tenant())
            await uow.tenants.add(
                synthetic_tenant(
                    tenant_id=TENANT_B_ID,
                    name="Synthetic Tenant B",
                )
            )
            await uow.sessions.add(
                synthetic_session(
                    token_hash=SESSION_TOKEN_HASH,
                )
            )
            await uow.commit()

        resolver = TenantContextResolver(uow_factory=platform_uow_factory)
        with pytest.raises(TenantAccessDeniedError, match=TENANT_ACCESS_DENIED_MESSAGE):
            await resolver.resolve(
                raw_token=RAW_TOKEN,
                tenant_id=TENANT_B_ID,
                correlation_id=CORRELATION_ID,
                now=NOW,
                touch_session=False,
            )

    asyncio.run(exercise())


def test_tenant_context_resolver_unavailable_for_missing_session(
    platform_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        resolver = TenantContextResolver(uow_factory=platform_uow_factory)

        with pytest.raises(TenantContextUnavailableError):
            await resolver.resolve(
                raw_token=RAW_TOKEN,
                tenant_id=TENANT_A_ID,
                correlation_id=CORRELATION_ID,
                now=NOW,
                touch_session=False,
            )

    asyncio.run(exercise())


def test_tenant_context_resolver_unavailable_for_suspended_tenant(
    platform_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = platform_uow_factory()
        async with uow:
            await uow.users.add(synthetic_user())
            await uow.tenants.add(
                synthetic_tenant(status=TenantStatus.SUSPENDED),
            )
            await uow.memberships.add(synthetic_membership())
            await uow.sessions.add(
                synthetic_session(
                    token_hash=SESSION_TOKEN_HASH,
                )
            )
            await uow.commit()

        resolver = TenantContextResolver(uow_factory=platform_uow_factory)
        with pytest.raises(TenantAccessDeniedError, match=TENANT_ACCESS_DENIED_MESSAGE):
            await resolver.resolve(
                raw_token=RAW_TOKEN,
                tenant_id=TENANT_A_ID,
                correlation_id=CORRELATION_ID,
                now=NOW,
                touch_session=False,
            )

    asyncio.run(exercise())


def test_tenant_context_resolver_unavailable_for_disabled_user(
    platform_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = platform_uow_factory()
        async with uow:
            await uow.users.add(User(id=USER_ID, status=UserStatus.DISABLED))
            await uow.tenants.add(synthetic_tenant())
            await uow.memberships.add(synthetic_membership())
            await uow.sessions.add(
                synthetic_session(
                    token_hash=SESSION_TOKEN_HASH,
                )
            )
            await uow.commit()

        resolver = TenantContextResolver(uow_factory=platform_uow_factory)
        with pytest.raises(TenantContextUnavailableError):
            await resolver.resolve(
                raw_token=RAW_TOKEN,
                tenant_id=TENANT_A_ID,
                correlation_id=CORRELATION_ID,
                now=NOW,
                touch_session=False,
            )

    asyncio.run(exercise())


def test_tenant_context_resolver_touches_session_last_seen(
    platform_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_authenticated_membership(platform_uow_factory)
        resolver = TenantContextResolver(
            uow_factory=platform_uow_factory,
            session_touch_interval=timedelta(minutes=1),
        )
        touch_time = NOW + timedelta(minutes=10)

        await resolver.resolve(
            raw_token=RAW_TOKEN,
            tenant_id=TENANT_A_ID,
            correlation_id=CORRELATION_ID,
            now=touch_time,
            touch_session=True,
        )

        lookup = platform_uow_factory()
        async with lookup:
            session = await lookup.sessions.get_by_token_hash(SESSION_TOKEN_HASH)

        assert session is not None
        assert session.last_seen_at == touch_time

    asyncio.run(exercise())


def test_tenant_listing_service_returns_active_tenants(
    platform_uow_factory: Any,
    tenant_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = platform_uow_factory()
        async with uow:
            await uow.users.add(synthetic_user())
            await uow.tenants.add(synthetic_tenant())
            await uow.tenants.add(
                synthetic_tenant(
                    tenant_id=TENANT_B_ID,
                    name="Synthetic Tenant B",
                    status=TenantStatus.SUSPENDED,
                )
            )
            await uow.memberships.add(synthetic_membership())
            await uow.memberships.add(
                synthetic_membership(
                    membership_id=UUID("00000000-0000-0000-0000-000000000021"),
                    tenant_id=TENANT_B_ID,
                )
            )
            await uow.commit()

        service = TenantListingService(uow_factory=tenant_uow_factory)
        accessible = await service.list_tenants_for_user(user_id=USER_ID)

        assert len(accessible) == 1
        tenant, membership = accessible[0]
        assert tenant.id == TENANT_A_ID
        assert membership.status is MembershipStatus.ACTIVE

    asyncio.run(exercise())


def test_tenant_context_resolver_rejects_non_token_type(platform_uow_factory: Any) -> None:
    resolver = TenantContextResolver(uow_factory=platform_uow_factory)

    with pytest.raises(TypeError, match="RawAuthenticationToken"):
        asyncio.run(
            resolver.resolve(
                raw_token="not-a-token",  # type: ignore[arg-type]
                tenant_id=TENANT_A_ID,
                correlation_id=CORRELATION_ID,
                now=NOW,
                touch_session=False,
            )
        )


def test_tenant_context_resolver_rejects_naive_now(platform_uow_factory: Any) -> None:
    resolver = TenantContextResolver(uow_factory=platform_uow_factory)

    with pytest.raises(ValueError, match="now must be timezone-aware"):
        asyncio.run(
            resolver.resolve(
                raw_token=RAW_TOKEN,
                tenant_id=TENANT_A_ID,
                correlation_id=CORRELATION_ID,
                now=LATER.replace(tzinfo=None),
                touch_session=False,
            )
        )
