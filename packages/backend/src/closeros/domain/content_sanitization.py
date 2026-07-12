"""Immutable persisted content sanitization domain entity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.domain.privacy_redaction import (
    SANITIZATION_POLICY_VERSION,
    AnalysisEligibility,
    SanitizationFailureCode,
    SanitizationStatus,
    validate_failure_code,
)


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
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class ContentSanitizationCategoryCount:
    category: str
    count: int

    def __post_init__(self) -> None:
        if not isinstance(self.category, str):
            raise TypeError("category must be a string")
        normalized = self.category.strip()
        if not normalized:
            raise ValueError("category must not be empty")
        object.__setattr__(self, "category", normalized)
        object.__setattr__(self, "count", _validate_non_negative_int(self.count, "count"))


@dataclass(frozen=True, slots=True)
class ContentSanitization:
    id: UUID
    tenant_id: UUID
    source_content_id: UUID
    sanitized_content_id: UUID | None
    source_resource_type: str
    source_resource_id: UUID
    policy_version: str
    detector_version: str
    status: SanitizationStatus
    analysis_eligibility: AnalysisEligibility
    total_finding_count: int
    critical_finding_count: int
    created_at: datetime
    completed_at: datetime | None
    failure_code: SanitizationFailureCode | None
    category_counts: tuple[ContentSanitizationCategoryCount, ...] = ()

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.source_content_id, "source_content_id")
        if self.sanitized_content_id is not None:
            _validate_uuid(self.sanitized_content_id, "sanitized_content_id")
        _validate_uuid(self.source_resource_id, "source_resource_id")

        for field_name in ("source_resource_type", "policy_version", "detector_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        if not isinstance(self.status, SanitizationStatus):
            raise TypeError("status must be a SanitizationStatus")
        if not isinstance(self.analysis_eligibility, AnalysisEligibility):
            raise TypeError("analysis_eligibility must be an AnalysisEligibility")

        total = _validate_non_negative_int(self.total_finding_count, "total_finding_count")
        critical = _validate_non_negative_int(
            self.critical_finding_count,
            "critical_finding_count",
        )
        if critical > total:
            raise ValueError("critical_finding_count must not exceed total_finding_count")

        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        if self.completed_at is not None:
            object.__setattr__(
                self,
                "completed_at",
                _validate_timezone_aware_datetime(self.completed_at, "completed_at"),
            )
        if self.failure_code is not None:
            object.__setattr__(self, "failure_code", validate_failure_code(self.failure_code))

        if not isinstance(self.category_counts, tuple):
            raise TypeError("category_counts must be a tuple")
        category_total = 0
        seen_categories: set[str] = set()
        for entry in self.category_counts:
            if not isinstance(entry, ContentSanitizationCategoryCount):
                raise TypeError("category_counts must contain ContentSanitizationCategoryCount")
            if entry.category in seen_categories:
                raise ValueError("duplicate category count")
            seen_categories.add(entry.category)
            category_total += entry.count
        if self.status is SanitizationStatus.COMPLETED and category_total != total:
            raise ValueError("category counts must sum to total_finding_count")


def default_policy_version() -> str:
    return SANITIZATION_POLICY_VERSION
