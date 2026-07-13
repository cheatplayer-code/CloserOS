"""Framework-independent retention purge execution domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class RetentionPurgeRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class RetentionPurgeBatchStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED_LEGAL_HOLD = "skipped_legal_hold"


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


def _validate_non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class RetentionPurgeRun:
    id: UUID
    tenant_id: UUID
    status: RetentionPurgeRunStatus
    dry_run: bool
    expires_before: datetime
    items_scanned: int
    items_deleted: int
    items_skipped_legal_hold: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    last_error_code: str | None = None
    claim_token: UUID | None = None
    claim_expires_at: datetime | None = None
    version: int = 1

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        if not isinstance(self.status, RetentionPurgeRunStatus):
            raise TypeError("status must be a RetentionPurgeRunStatus")
        if not isinstance(self.dry_run, bool):
            raise TypeError("dry_run must be a bool")
        if not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if self.claim_token is not None:
            _validate_uuid(self.claim_token, "claim_token")
        if self.claim_expires_at is not None:
            object.__setattr__(
                self,
                "claim_expires_at",
                _validate_timezone_aware_datetime(self.claim_expires_at, "claim_expires_at"),
            )
        object.__setattr__(
            self,
            "expires_before",
            _validate_timezone_aware_datetime(self.expires_before, "expires_before"),
        )
        object.__setattr__(
            self, "items_scanned", _validate_non_negative_int(self.items_scanned, "items_scanned")
        )
        object.__setattr__(
            self, "items_deleted", _validate_non_negative_int(self.items_deleted, "items_deleted")
        )
        object.__setattr__(
            self,
            "items_skipped_legal_hold",
            _validate_non_negative_int(self.items_skipped_legal_hold, "items_skipped_legal_hold"),
        )
        if self.started_at is not None:
            object.__setattr__(
                self,
                "started_at",
                _validate_timezone_aware_datetime(self.started_at, "started_at"),
            )
        if self.completed_at is not None:
            object.__setattr__(
                self,
                "completed_at",
                _validate_timezone_aware_datetime(self.completed_at, "completed_at"),
            )
        object.__setattr__(
            self,
            "created_at",
            _validate_timezone_aware_datetime(self.created_at, "created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _validate_timezone_aware_datetime(self.updated_at, "updated_at"),
        )

    def __repr__(self) -> str:
        return (
            "RetentionPurgeRun("
            f"id={self.id!s}, "
            f"tenant_id={self.tenant_id!s}, "
            f"status={self.status.value!r}, "
            f"dry_run={self.dry_run}"
            ")"
        )


@dataclass(frozen=True, slots=True)
class RetentionPurgeBatch:
    id: UUID
    tenant_id: UUID
    purge_run_id: UUID
    deleted_content_id: UUID
    status: RetentionPurgeBatchStatus
    created_at: datetime
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.purge_run_id, "purge_run_id")
        _validate_uuid(self.deleted_content_id, "deleted_content_id")
        if not isinstance(self.status, RetentionPurgeBatchStatus):
            raise TypeError("status must be a RetentionPurgeBatchStatus")
        object.__setattr__(
            self,
            "created_at",
            _validate_timezone_aware_datetime(self.created_at, "created_at"),
        )
        if self.completed_at is not None:
            object.__setattr__(
                self,
                "completed_at",
                _validate_timezone_aware_datetime(self.completed_at, "completed_at"),
            )

    def __repr__(self) -> str:
        return (
            "RetentionPurgeBatch("
            f"id={self.id!s}, "
            f"purge_run_id={self.purge_run_id!s}, "
            f"status={self.status.value!r}"
            ")"
        )


__all__ = [
    "RetentionPurgeBatch",
    "RetentionPurgeBatchStatus",
    "RetentionPurgeRun",
    "RetentionPurgeRunStatus",
]
