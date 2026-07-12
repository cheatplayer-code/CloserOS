"""Application-layer persistence ports for tenant, membership, and invitation."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

from closeros.application.audit_persistence import AuditEventAppendRepository
from closeros.application.persistence_errors import PersistenceError
from closeros.domain.identity import (
    MembershipStatus,
    Role,
    TenantStatus,
)
from closeros.domain.invitation import Invitation
from closeros.domain.membership import Membership
from closeros.domain.tenant import Tenant


class TenantPersistenceError(PersistenceError):
    """Base class for safe tenant persistence failures."""


class TenantRecordNotFoundError(TenantPersistenceError):
    """Raised when an update targets a record that does not exist."""


class DuplicateMembershipError(TenantPersistenceError):
    """Raised when a tenant already has a membership for the user."""


class TenantReferenceError(TenantPersistenceError):
    """Raised when a referenced tenant, user, or membership does not exist."""


class TenantRepository(Protocol):
    async def add(self, tenant: Tenant) -> None: ...

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None: ...

    async def update_status(
        self,
        *,
        tenant_id: UUID,
        status: TenantStatus,
    ) -> None: ...

    async def list_for_user(self, user_id: UUID) -> tuple[Tenant, ...]: ...


class MembershipRepository(Protocol):
    async def add(self, membership: Membership) -> None: ...

    async def get_by_id(
        self,
        tenant_id: UUID,
        membership_id: UUID,
    ) -> Membership | None: ...

    async def get_by_tenant_and_user(
        self,
        tenant_id: UUID,
        user_id: UUID,
    ) -> Membership | None: ...

    async def list_for_tenant(self, tenant_id: UUID) -> tuple[Membership, ...]: ...

    async def list_for_user(self, user_id: UUID) -> tuple[Membership, ...]: ...

    async def update_status(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        status: MembershipStatus,
    ) -> None: ...

    async def replace_roles(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        roles: frozenset[Role],
    ) -> None: ...


class InvitationRepository(Protocol):
    async def add(self, invitation: Invitation) -> None: ...

    async def get_by_id(
        self,
        tenant_id: UUID,
        invitation_id: UUID,
    ) -> Invitation | None: ...

    async def list_for_tenant(self, tenant_id: UUID) -> tuple[Invitation, ...]: ...

    async def revoke(
        self,
        *,
        tenant_id: UUID,
        invitation_id: UUID,
    ) -> None: ...


class TenantUnitOfWork(Protocol):
    tenants: TenantRepository
    memberships: MembershipRepository
    invitations: InvitationRepository
    audit_events: AuditEventAppendRepository

    async def __aenter__(self) -> TenantUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
