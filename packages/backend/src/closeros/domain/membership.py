"""Framework-independent membership domain entity."""

from dataclasses import dataclass
from uuid import UUID

from closeros.domain.identity import MembershipStatus, Role


@dataclass(slots=True)
class Membership:
    id: UUID
    tenant_id: UUID
    user_id: UUID
    roles: frozenset[Role]
    status: MembershipStatus

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID")

        if not isinstance(self.tenant_id, UUID):
            raise TypeError("tenant_id must be a UUID")

        if not isinstance(self.user_id, UUID):
            raise TypeError("user_id must be a UUID")

        if not isinstance(self.roles, frozenset):
            raise TypeError("roles must be a frozenset")

        if not self.roles:
            raise ValueError("roles must not be empty")

        if any(not isinstance(role, Role) for role in self.roles):
            raise TypeError("roles must contain only Role values")

        if not isinstance(self.status, MembershipStatus):
            raise TypeError("status must be a MembershipStatus")
