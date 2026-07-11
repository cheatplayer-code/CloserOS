"""Framework-independent tenant domain entity."""

from dataclasses import dataclass
from uuid import UUID

from closeros.domain.identity import TenantStatus


@dataclass(slots=True)
class Tenant:
    id: UUID
    name: str
    status: TenantStatus
    time_zone: str

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

        if not isinstance(self.time_zone, str):
            raise TypeError("time_zone must be a string")

        normalized_time_zone = self.time_zone.strip()

        if not normalized_time_zone:
            raise ValueError("time_zone must not be empty")

        self.name = normalized_name
        self.time_zone = normalized_time_zone
