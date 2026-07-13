"""Operator bootstrap for attaching the first tenant to a verified user."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from closeros.application.audit_recording import append_required_audit_event
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.tenant_persistence import DuplicateMembershipError
from closeros.domain.audit import (
    AuditAction,
    AuditActorType,
    AuditScope,
    AuditTargetType,
    build_audit_event,
)
from closeros.domain.authentication import AuthenticationEmail
from closeros.domain.identity import MembershipStatus, Role, TenantStatus, UserStatus
from closeros.domain.membership import Membership
from closeros.domain.retention import RetentionPolicy
from closeros.domain.tenant import Tenant
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]


class BootstrapTenantError(Exception):
    """Base class for bootstrap failures."""


class BootstrapUserNotFoundError(BootstrapTenantError):
    """Raised when the owner email is not registered."""


class BootstrapUserInactiveError(BootstrapTenantError):
    """Raised when the owner account is inactive."""


class BootstrapEmailNotVerifiedError(BootstrapTenantError):
    """Raised when the owner email is not verified."""


class BootstrapInvalidArgumentError(BootstrapTenantError):
    """Raised when bootstrap inputs are invalid."""


class BootstrapOwnershipConflictError(BootstrapTenantError):
    """Raised when the owner already belongs to the tenant name without owner role."""


@dataclass(frozen=True, slots=True)
class BootstrapTenantResult:
    status: str
    tenant_id: UUID
    owner_user_id: UUID
    roles: tuple[str, ...]


def _normalize_email(value: str) -> AuthenticationEmail:
    try:
        return AuthenticationEmail(value)
    except ValueError as error:
        raise BootstrapInvalidArgumentError("owner email is invalid") from error


def _default_retention_policy() -> RetentionPolicy:
    return RetentionPolicy(
        raw_message_days=30,
        sanitized_message_days=30,
        ai_output_days=30,
        audit_log_days=365,
        backup_days=30,
        post_contract_deletion_days=90,
    )


def _advisory_lock_key(*, user_id: UUID, tenant_name: str) -> int:
    material = f"{user_id}:{tenant_name.strip().lower()}".encode()
    return int.from_bytes(material[:8].ljust(8, b"\0"), "big", signed=True)


class BootstrapTenantService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        uuid_factory: _UuidFactory,
        clock: _Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._uuid_factory = uuid_factory
        self._clock = clock

    async def bootstrap_owner_tenant(
        self,
        *,
        owner_email: str,
        tenant_name: str,
        time_zone: str,
        dry_run: bool = False,
    ) -> BootstrapTenantResult:
        normalized_email = _normalize_email(owner_email)
        normalized_name = tenant_name.strip()
        normalized_time_zone = time_zone.strip()
        if not normalized_name:
            raise BootstrapInvalidArgumentError("tenant name is required")
        if not normalized_time_zone:
            raise BootstrapInvalidArgumentError("time zone is required")

        uow = self._uow_factory()
        async with uow:
            credential = await uow.credentials.get_by_email(normalized_email)
            if credential is None:
                raise BootstrapUserNotFoundError("owner user does not exist")
            if credential.email_verified_at is None:
                raise BootstrapEmailNotVerifiedError("owner email is not verified")

            user = await uow.users.get_by_id(credential.user_id)
            if user is None:
                raise BootstrapUserNotFoundError("owner user does not exist")
            if user.status is not UserStatus.ACTIVE:
                raise BootstrapUserInactiveError("owner user is inactive")

            existing = await self._find_existing_owner_membership(
                uow,
                user_id=user.id,
                tenant_name=normalized_name,
            )
            if existing is not None:
                tenant_id, membership = existing
                return BootstrapTenantResult(
                    status="existing",
                    tenant_id=tenant_id,
                    owner_user_id=user.id,
                    roles=tuple(sorted(role.value for role in membership.roles)),
                )

            conflict = await self._find_non_owner_name_conflict(
                uow,
                user_id=user.id,
                tenant_name=normalized_name,
            )
            if conflict is not None:
                raise BootstrapOwnershipConflictError(
                    "owner already belongs to a tenant with this name without owner role"
                )

            if dry_run:
                return BootstrapTenantResult(
                    status="dry_run",
                    tenant_id=self._uuid_factory(),
                    owner_user_id=user.id,
                    roles=(Role.OWNER.value,),
                )

            if isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
                lock_key = _advisory_lock_key(user_id=user.id, tenant_name=normalized_name)
                await uow.session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": lock_key},
                )

            existing_after_lock = await self._find_existing_owner_membership(
                uow,
                user_id=user.id,
                tenant_name=normalized_name,
            )
            if existing_after_lock is not None:
                tenant_id, membership = existing_after_lock
                return BootstrapTenantResult(
                    status="existing",
                    tenant_id=tenant_id,
                    owner_user_id=user.id,
                    roles=tuple(sorted(role.value for role in membership.roles)),
                )

            now = self._clock()
            tenant_id = self._uuid_factory()
            membership_id = self._uuid_factory()
            audit_event_id = self._uuid_factory()
            correlation_id = self._uuid_factory()

            tenant = Tenant(
                id=tenant_id,
                name=normalized_name,
                status=TenantStatus.ACTIVE,
                time_zone=normalized_time_zone,
                retention_policy=_default_retention_policy(),
            )
            membership = Membership(
                id=membership_id,
                tenant_id=tenant_id,
                user_id=user.id,
                roles=frozenset({Role.OWNER}),
                status=MembershipStatus.ACTIVE,
            )
            audit_event = build_audit_event(
                event_id=audit_event_id,
                scope=AuditScope.TENANT,
                tenant_id=tenant_id,
                actor_type=AuditActorType.USER,
                actor_id=user.id,
                action=AuditAction.MEMBERSHIP_CREATED,
                target_type=AuditTargetType.MEMBERSHIP,
                target_id=membership_id,
                occurred_at=now,
                correlation_id=correlation_id,
                metadata={"source": "bootstrap_tenant", "outcome": "created"},
            )

            await uow.tenants.add(tenant)
            try:
                await uow.memberships.add(membership)
            except DuplicateMembershipError as error:
                raise BootstrapOwnershipConflictError(
                    "owner membership already exists for tenant"
                ) from error
            await append_required_audit_event(
                uow.audit_events,
                audit_event,
            )
            await uow.commit()

            return BootstrapTenantResult(
                status="created",
                tenant_id=tenant_id,
                owner_user_id=user.id,
                roles=(Role.OWNER.value,),
            )

    async def _find_existing_owner_membership(
        self,
        uow: IntegratedUnitOfWork,
        *,
        user_id: UUID,
        tenant_name: str,
    ) -> tuple[UUID, Membership] | None:
        memberships = await uow.memberships.list_for_user(user_id)
        for membership in memberships:
            if Role.OWNER not in membership.roles:
                continue
            tenant = await uow.tenants.get_by_id(membership.tenant_id)
            if tenant is not None and tenant.name == tenant_name:
                return tenant.id, membership
        return None

    async def _find_non_owner_name_conflict(
        self,
        uow: IntegratedUnitOfWork,
        *,
        user_id: UUID,
        tenant_name: str,
    ) -> Membership | None:
        memberships = await uow.memberships.list_for_user(user_id)
        for membership in memberships:
            if Role.OWNER in membership.roles:
                continue
            tenant = await uow.tenants.get_by_id(membership.tenant_id)
            if tenant is not None and tenant.name == tenant_name:
                return membership
        return None
