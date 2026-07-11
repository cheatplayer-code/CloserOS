"""Framework-independent tenant domain entity."""

from dataclasses import dataclass
from uuid import UUID

from closeros.domain.identity import TenantStatus


@dataclass(slots=True)
class Tenant:
    id: UUID
    name: str
    status: TenantStatus

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID")

        if not isinstance(self.name, str):
            raise TypeError("name must be a string")

        normalized_name = self.name.strip()

        if not normalized_name:
            raise ValueError("name must not be empty")

        if not isinstance(self.status, TenantStatus):
            raise TypeError("status must be a TenantStatus")

        self.name = normalized_name
