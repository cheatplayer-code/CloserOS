"""PostgreSQL integration tests for tenant repositories."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest
from closeros.application.persistence_errors import TenantMismatchError
from closeros.application.tenant_persistence import (
    DuplicateMembershipError,
    TenantRecordNotFoundError,
    TenantReferenceError,
)
from closeros.domain.identity import InvitationStatus, MembershipStatus, TenantStatus

from tests.auth_persistence_support import OTHER_USER_ID, USER_ID, synthetic_user
from tests.tenant_persistence_support import (
    ANALYST_ROLES,
    INVITATION_A_ID,
    INVITATION_B_ID,
    MANAGER_ROLES,
    MEMBERSHIP_A_ID,
    MEMBERSHIP_B_ID,
    OTHER_INVITE_EMAIL,
    OWNER_ROLES,
    TENANT_A_ID,
    TENANT_B_ID,
    synthetic_invitation,
    synthetic_membership,
    synthetic_tenant,
)

pytestmark = pytest.mark.platform_persistence


async def _seed_user(platform_uow_factory: Any, *, user_id: UUID = USER_ID) -> None:
    uow = platform_uow_factory()
    async with uow:
        await uow.users.add(synthetic_user(user_id=user_id))
        await uow.commit()


async def _seed_tenant_with_membership(
    platform_uow_factory: Any,
    tenant_uow_factory: Any,
    *,
    tenant_id: UUID = TENANT_A_ID,
    user_id: UUID = USER_ID,
    membership_id: UUID = MEMBERSHIP_A_ID,
) -> None:
    await _seed_user(platform_uow_factory, user_id=user_id)
    uow = tenant_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant(tenant_id=tenant_id))
        await uow.memberships.add(
            synthetic_membership(
                membership_id=membership_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        )
        await uow.commit()


def test_tenant_repository_add_and_get(tenant_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = tenant_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.commit()

        lookup = tenant_uow_factory()
        async with lookup:
            restored = await lookup.tenants.get_by_id(TENANT_A_ID)

        assert restored is not None
        assert restored.name == "Synthetic Tenant A"
        assert restored.status is TenantStatus.ACTIVE

    asyncio.run(exercise())


def test_tenant_repository_update_status(tenant_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = tenant_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.tenants.update_status(tenant_id=TENANT_A_ID, status=TenantStatus.SUSPENDED)
            await uow.commit()

        lookup = tenant_uow_factory()
        async with lookup:
            restored = await lookup.tenants.get_by_id(TENANT_A_ID)

        assert restored is not None
        assert restored.status is TenantStatus.SUSPENDED

    asyncio.run(exercise())


def test_tenant_repository_update_status_missing_record_raises(
    tenant_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = tenant_uow_factory()
        async with uow:
            with pytest.raises(TenantRecordNotFoundError, match="tenant not found"):
                await uow.tenants.update_status(
                    tenant_id=TENANT_A_ID,
                    status=TenantStatus.SUSPENDED,
                )
            await uow.rollback()

    asyncio.run(exercise())


def test_membership_repository_round_trip_with_roles(
    platform_uow_factory: Any,
    tenant_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_user(platform_uow_factory)
        uow = tenant_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.memberships.add(
                synthetic_membership(roles=OWNER_ROLES | MANAGER_ROLES),
            )
            await uow.commit()

        lookup = tenant_uow_factory()
        async with lookup:
            restored = await lookup.memberships.get_by_id(TENANT_A_ID, MEMBERSHIP_A_ID)

        assert restored is not None
        assert restored.roles == OWNER_ROLES | MANAGER_ROLES

    asyncio.run(exercise())


def test_membership_repository_get_by_tenant_and_user(
    platform_uow_factory: Any,
    tenant_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_tenant_with_membership(platform_uow_factory, tenant_uow_factory)

        lookup = tenant_uow_factory()
        async with lookup:
            restored = await lookup.memberships.get_by_tenant_and_user(TENANT_A_ID, USER_ID)

        assert restored is not None
        assert restored.id == MEMBERSHIP_A_ID

    asyncio.run(exercise())


def test_membership_repository_list_for_tenant_and_user(
    platform_uow_factory: Any,
    tenant_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_user(platform_uow_factory)
        await _seed_user(platform_uow_factory, user_id=OTHER_USER_ID)
        uow = tenant_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.tenants.add(
                synthetic_tenant(
                    tenant_id=TENANT_B_ID,
                    name="Synthetic Tenant B",
                )
            )
            await uow.memberships.add(synthetic_membership())
            await uow.memberships.add(
                synthetic_membership(
                    membership_id=MEMBERSHIP_B_ID,
                    tenant_id=TENANT_B_ID,
                    user_id=OTHER_USER_ID,
                )
            )
            await uow.commit()

        lookup = tenant_uow_factory()
        async with lookup:
            tenant_memberships = await lookup.memberships.list_for_tenant(TENANT_A_ID)
            user_memberships = await lookup.memberships.list_for_user(USER_ID)

        assert len(tenant_memberships) == 1
        assert len(user_memberships) == 1
        assert user_memberships[0].tenant_id == TENANT_A_ID

    asyncio.run(exercise())


def test_membership_repository_enforces_unique_tenant_user(
    platform_uow_factory: Any,
    tenant_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_user(platform_uow_factory)
        uow = tenant_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.memberships.add(synthetic_membership())
            with pytest.raises(DuplicateMembershipError):
                await uow.memberships.add(
                    synthetic_membership(
                        membership_id=MEMBERSHIP_B_ID,
                    )
                )
                await uow.commit()
            await uow.rollback()

    asyncio.run(exercise())


def test_membership_repository_rejects_missing_user(
    tenant_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = tenant_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            with pytest.raises(TenantReferenceError):
                await uow.memberships.add(synthetic_membership())
                await uow.commit()
            await uow.rollback()

    asyncio.run(exercise())


def test_membership_repository_update_status_and_replace_roles(
    platform_uow_factory: Any,
    tenant_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_tenant_with_membership(platform_uow_factory, tenant_uow_factory)

        update = tenant_uow_factory()
        async with update:
            await update.memberships.update_status(
                tenant_id=TENANT_A_ID,
                membership_id=MEMBERSHIP_A_ID,
                status=MembershipStatus.SUSPENDED,
            )
            await update.memberships.replace_roles(
                tenant_id=TENANT_A_ID,
                membership_id=MEMBERSHIP_A_ID,
                roles=ANALYST_ROLES,
            )
            await update.commit()

        lookup = tenant_uow_factory()
        async with lookup:
            restored = await lookup.memberships.get_by_id(TENANT_A_ID, MEMBERSHIP_A_ID)

        assert restored is not None
        assert restored.status is MembershipStatus.SUSPENDED
        assert restored.roles == ANALYST_ROLES

    asyncio.run(exercise())


def test_membership_repository_denies_cross_tenant_lookup(
    platform_uow_factory: Any,
    tenant_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_tenant_with_membership(platform_uow_factory, tenant_uow_factory)

        lookup = tenant_uow_factory()
        async with lookup:
            with pytest.raises(TenantMismatchError, match="tenant scope mismatch"):
                await lookup.memberships.get_by_id(TENANT_B_ID, MEMBERSHIP_A_ID)

    asyncio.run(exercise())


def test_invitation_repository_round_trip(tenant_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = tenant_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.invitations.add(synthetic_invitation())
            await uow.commit()

        lookup = tenant_uow_factory()
        async with lookup:
            restored = await lookup.invitations.get_by_id(TENANT_A_ID, INVITATION_A_ID)
            listed = await lookup.invitations.list_for_tenant(TENANT_A_ID)

        assert restored is not None
        assert restored.email == "invite.synthetic@example.test"
        assert restored.roles == MANAGER_ROLES
        assert len(listed) == 1

    asyncio.run(exercise())


def test_invitation_repository_revoke(tenant_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = tenant_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.invitations.add(synthetic_invitation())
            await uow.invitations.revoke(tenant_id=TENANT_A_ID, invitation_id=INVITATION_A_ID)
            await uow.commit()

        lookup = tenant_uow_factory()
        async with lookup:
            restored = await lookup.invitations.get_by_id(TENANT_A_ID, INVITATION_A_ID)

        assert restored is not None
        assert restored.status is InvitationStatus.REVOKED

    asyncio.run(exercise())


def test_invitation_repository_denies_cross_tenant_lookup(tenant_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = tenant_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.invitations.add(synthetic_invitation())
            await uow.commit()

        lookup = tenant_uow_factory()
        async with lookup:
            with pytest.raises(TenantMismatchError, match="tenant scope mismatch"):
                await lookup.invitations.get_by_id(TENANT_B_ID, INVITATION_A_ID)

    asyncio.run(exercise())


def test_tenant_repository_list_for_user(
    platform_uow_factory: Any,
    tenant_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_tenant_with_membership(platform_uow_factory, tenant_uow_factory)

        lookup = tenant_uow_factory()
        async with lookup:
            tenants = await lookup.tenants.list_for_user(USER_ID)

        assert len(tenants) == 1
        assert tenants[0].id == TENANT_A_ID

    asyncio.run(exercise())


def test_invitation_repository_stores_multiple_roles(tenant_uow_factory: Any) -> None:
    async def exercise() -> None:
        roles = OWNER_ROLES | ANALYST_ROLES
        uow = tenant_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.invitations.add(
                synthetic_invitation(
                    invitation_id=INVITATION_B_ID,
                    email=OTHER_INVITE_EMAIL,
                    roles=roles,
                )
            )
            await uow.commit()

        lookup = tenant_uow_factory()
        async with lookup:
            restored = await lookup.invitations.get_by_id(TENANT_A_ID, INVITATION_B_ID)

        assert restored is not None
        assert restored.roles == roles

    asyncio.run(exercise())
