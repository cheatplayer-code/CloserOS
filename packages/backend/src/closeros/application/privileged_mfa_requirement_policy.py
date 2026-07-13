"""Privileged membership MFA requirement policy for production login."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.domain.authentication_policy import requires_mfa_for_roles
from closeros.domain.identity import MembershipStatus

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]


@dataclass(frozen=True, slots=True)
class PrivilegedMembershipMfaRequirementPolicy:
    """Requires MFA when the user holds privileged roles in any active membership."""

    uow_factory: _UnitOfWorkFactory

    async def requires_mfa_for_user(self, *, user_id: UUID) -> bool:
        uow = self.uow_factory()
        async with uow:
            memberships = await uow.memberships.list_for_user(user_id)
        for membership in memberships:
            if membership.status is MembershipStatus.ACTIVE and requires_mfa_for_roles(
                membership.roles
            ):
                return True
        return False


__all__ = ["PrivilegedMembershipMfaRequirementPolicy"]
