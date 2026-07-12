"""Framework-independent manager assignment domain entity."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


def _validate_uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")

    return value


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")

    return value


@dataclass(frozen=True, slots=True)
class ManagerAssignment:
    id: UUID
    tenant_id: UUID
    manager_user_id: UUID
    conversation_thread_id: UUID | None
    sales_case_id: UUID | None
    assigned_at: datetime

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.manager_user_id, "manager_user_id")

        has_thread_target = self.conversation_thread_id is not None
        has_sales_case_target = self.sales_case_id is not None

        if has_thread_target == has_sales_case_target:
            raise ValueError("exactly one of conversation_thread_id or sales_case_id must be set")

        if self.conversation_thread_id is not None:
            _validate_uuid(self.conversation_thread_id, "conversation_thread_id")

        if self.sales_case_id is not None:
            _validate_uuid(self.sales_case_id, "sales_case_id")

        object.__setattr__(
            self,
            "assigned_at",
            _validate_timezone_aware_datetime(self.assigned_at, "assigned_at"),
        )
