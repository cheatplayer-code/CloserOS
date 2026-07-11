"""Framework-independent retention policy value object."""

from dataclasses import dataclass


def _validate_retention_days(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")

    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to zero")

    return value


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    raw_message_days: int
    sanitized_message_days: int
    ai_output_days: int
    audit_log_days: int
    backup_days: int
    post_contract_deletion_days: int

    def __post_init__(self) -> None:
        _validate_retention_days(self.raw_message_days, "raw_message_days")
        _validate_retention_days(self.sanitized_message_days, "sanitized_message_days")
        _validate_retention_days(self.ai_output_days, "ai_output_days")
        _validate_retention_days(self.audit_log_days, "audit_log_days")
        _validate_retention_days(self.backup_days, "backup_days")
        _validate_retention_days(
            self.post_contract_deletion_days,
            "post_contract_deletion_days",
        )
