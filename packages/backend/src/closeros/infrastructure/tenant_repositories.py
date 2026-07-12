"""PostgreSQL repository implementations for tenant persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.tenant_persistence import (
    DuplicateMembershipError,
    TenantPersistenceError,
    TenantRecordNotFoundError,
    TenantReferenceError,
)
from closeros.domain.identity import (
    InvitationStatus,
    MembershipStatus,
    Role,
    TenantStatus,
)
from closeros.domain.invitation import Invitation
from closeros.domain.membership import Membership
from closeros.domain.tenant import Tenant
from closeros.infrastructure import tenant_mappers as mappers
from closeros.infrastructure.persistence_errors import translate_integrity_error
from closeros.infrastructure.repository_helpers import (
    tenant_scoped_get,
    tenant_scoped_get_required,
)
from closeros.infrastructure.tenant_orm import (
    InvitationRoleRow,
    InvitationRow,
    MembershipRoleRow,
    MembershipRow,
    TenantRow,
)

_CONSTRAINT_ERRORS: dict[str, type[TenantPersistenceError]] = {
    "tenant_id_user_id": DuplicateMembershipError,
    "uq_memberships_tenant_id_user_id": DuplicateMembershipError,
    "fk_memberships_tenant_id_tenants": TenantReferenceError,
    "fk_memberships_user_id_users": TenantReferenceError,
    "fk_membership_roles_membership_id_memberships": TenantReferenceError,
    "fk_invitations_tenant_id_tenants": TenantReferenceError,
    "fk_invitation_roles_invitation_id_invitations": TenantReferenceError,
}


def _translate_integrity_error(error: IntegrityError) -> TenantPersistenceError:
    return translate_integrity_error(
        error,
        constraint_errors=_CONSTRAINT_ERRORS,
        default=TenantPersistenceError,
        message="tenant persistence integrity error",
    )


async def _load_membership_roles(
    session: AsyncSession,
    membership_ids: tuple[UUID, ...],
) -> dict[UUID, frozenset[Role]]:
    if not membership_ids:
        return {}

    rows = (
        (
            await session.execute(
                select(MembershipRoleRow).where(MembershipRoleRow.membership_id.in_(membership_ids))
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[UUID, set[Role]] = {membership_id: set() for membership_id in membership_ids}
    for row in rows:
        grouped[row.membership_id].add(Role(row.role))
    return {membership_id: frozenset(roles) for membership_id, roles in grouped.items()}


async def _load_invitation_roles(
    session: AsyncSession,
    invitation_ids: tuple[UUID, ...],
) -> dict[UUID, frozenset[Role]]:
    if not invitation_ids:
        return {}

    rows = (
        (
            await session.execute(
                select(InvitationRoleRow).where(InvitationRoleRow.invitation_id.in_(invitation_ids))
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[UUID, set[Role]] = {invitation_id: set() for invitation_id in invitation_ids}
    for row in rows:
        grouped[row.invitation_id].add(Role(row.role))
    return {invitation_id: frozenset(roles) for invitation_id, roles in grouped.items()}


class SqlAlchemyTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, tenant: Tenant) -> None:
        self._session.add(mappers.tenant_to_row(tenant))
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        row = await self._session.get(TenantRow, tenant_id)
        return None if row is None else mappers.tenant_to_domain(row)

    async def update_status(self, *, tenant_id: UUID, status: TenantStatus) -> None:
        row = await self._session.get(TenantRow, tenant_id)
        if row is None:
            raise TenantRecordNotFoundError("tenant not found")
        row.status = status.value
        await self._session.flush()

    async def list_for_user(self, user_id: UUID) -> tuple[Tenant, ...]:
        rows = (
            (
                await self._session.execute(
                    select(TenantRow)
                    .join(MembershipRow, MembershipRow.tenant_id == TenantRow.id)
                    .where(
                        MembershipRow.user_id == user_id,
                        MembershipRow.status == MembershipStatus.ACTIVE.value,
                    )
                    .order_by(TenantRow.name, TenantRow.id)
                )
            )
            .scalars()
            .all()
        )
        return tuple(mappers.tenant_to_domain(row) for row in rows)


class SqlAlchemyMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, membership: Membership) -> None:
        self._session.add(mappers.membership_to_row(membership))
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error
        for role_row in mappers.membership_role_rows(membership.id, membership.roles):
            self._session.add(role_row)
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error

    async def get_by_id(
        self,
        tenant_id: UUID,
        membership_id: UUID,
    ) -> Membership | None:
        row = await tenant_scoped_get(
            self._session,
            MembershipRow,
            tenant_id=tenant_id,
            record_id=membership_id,
        )
        if row is None:
            return None
        roles = await _load_membership_roles(self._session, (row.id,))
        return mappers.membership_to_domain(row, roles[row.id])

    async def get_by_tenant_and_user(
        self,
        tenant_id: UUID,
        user_id: UUID,
    ) -> Membership | None:
        row = (
            await self._session.execute(
                select(MembershipRow).where(
                    MembershipRow.tenant_id == tenant_id,
                    MembershipRow.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        roles = await _load_membership_roles(self._session, (row.id,))
        return mappers.membership_to_domain(row, roles[row.id])

    async def list_for_tenant(self, tenant_id: UUID) -> tuple[Membership, ...]:
        rows = (
            (
                await self._session.execute(
                    select(MembershipRow)
                    .where(MembershipRow.tenant_id == tenant_id)
                    .order_by(MembershipRow.id)
                )
            )
            .scalars()
            .all()
        )
        membership_ids = tuple(row.id for row in rows)
        role_map = await _load_membership_roles(self._session, membership_ids)
        return tuple(mappers.membership_to_domain(row, role_map[row.id]) for row in rows)

    async def list_for_user(self, user_id: UUID) -> tuple[Membership, ...]:
        rows = (
            (
                await self._session.execute(
                    select(MembershipRow)
                    .where(MembershipRow.user_id == user_id)
                    .order_by(MembershipRow.tenant_id, MembershipRow.id)
                )
            )
            .scalars()
            .all()
        )
        membership_ids = tuple(row.id for row in rows)
        role_map = await _load_membership_roles(self._session, membership_ids)
        return tuple(mappers.membership_to_domain(row, role_map[row.id]) for row in rows)

    async def update_status(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        status: MembershipStatus,
    ) -> None:
        row = await tenant_scoped_get_required(
            self._session,
            MembershipRow,
            tenant_id=tenant_id,
            record_id=membership_id,
            not_found_error=TenantRecordNotFoundError,
            not_found_message="membership not found",
        )
        row.status = status.value
        await self._session.flush()

    async def replace_roles(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        roles: frozenset[Role],
    ) -> None:
        await tenant_scoped_get_required(
            self._session,
            MembershipRow,
            tenant_id=tenant_id,
            record_id=membership_id,
            not_found_error=TenantRecordNotFoundError,
            not_found_message="membership not found",
        )
        await self._session.execute(
            delete(MembershipRoleRow).where(MembershipRoleRow.membership_id == membership_id)
        )
        for role_row in mappers.membership_role_rows(membership_id, roles):
            self._session.add(role_row)
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error


class SqlAlchemyInvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, invitation: Invitation) -> None:
        self._session.add(mappers.invitation_to_row(invitation))
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error
        for role_row in mappers.invitation_role_rows(invitation.id, invitation.roles):
            self._session.add(role_row)
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error

    async def get_by_id(
        self,
        tenant_id: UUID,
        invitation_id: UUID,
    ) -> Invitation | None:
        row = await tenant_scoped_get(
            self._session,
            InvitationRow,
            tenant_id=tenant_id,
            record_id=invitation_id,
        )
        if row is None:
            return None
        roles = await _load_invitation_roles(self._session, (row.id,))
        return mappers.invitation_to_domain(row, roles[row.id])

    async def list_for_tenant(self, tenant_id: UUID) -> tuple[Invitation, ...]:
        rows = (
            (
                await self._session.execute(
                    select(InvitationRow)
                    .where(InvitationRow.tenant_id == tenant_id)
                    .order_by(InvitationRow.expires_at, InvitationRow.id)
                )
            )
            .scalars()
            .all()
        )
        invitation_ids = tuple(row.id for row in rows)
        role_map = await _load_invitation_roles(self._session, invitation_ids)
        return tuple(mappers.invitation_to_domain(row, role_map[row.id]) for row in rows)

    async def revoke(
        self,
        *,
        tenant_id: UUID,
        invitation_id: UUID,
    ) -> None:
        row = await tenant_scoped_get_required(
            self._session,
            InvitationRow,
            tenant_id=tenant_id,
            record_id=invitation_id,
            not_found_error=TenantRecordNotFoundError,
            not_found_message="invitation not found",
        )
        row.status = InvitationStatus.REVOKED.value
        await self._session.flush()
