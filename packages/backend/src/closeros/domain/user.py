"""Framework-independent user domain entity."""

from dataclasses import dataclass
from uuid import UUID

from closeros.domain.identity import UserStatus


@dataclass(slots=True)
class User:
    id: UUID
    status: UserStatus

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID")

        if not isinstance(self.status, UserStatus):
            raise TypeError("status must be a UserStatus")
