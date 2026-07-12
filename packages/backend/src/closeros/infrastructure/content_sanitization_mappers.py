"""Domain ↔ ORM mappers for content sanitization persistence."""

from __future__ import annotations

from uuid import UUID

from closeros.domain.content_sanitization import (
    ContentSanitization,
    ContentSanitizationCategoryCount,
)
from closeros.domain.privacy_redaction import (
    AnalysisEligibility,
    SanitizationFailureCode,
    SanitizationStatus,
)
from closeros.infrastructure.content_sanitization_orm import (
    ContentSanitizationCategoryCountRow,
    ContentSanitizationRow,
)


def to_domain(
    row: ContentSanitizationRow,
    *,
    category_rows: tuple[ContentSanitizationCategoryCountRow, ...],
) -> ContentSanitization:
    return ContentSanitization(
        id=row.id,
        tenant_id=row.tenant_id,
        source_content_id=row.source_content_id,
        sanitized_content_id=row.sanitized_content_id,
        source_resource_type=row.source_resource_type,
        source_resource_id=row.source_resource_id,
        policy_version=row.policy_version,
        detector_version=row.detector_version,
        status=SanitizationStatus(row.status),
        analysis_eligibility=AnalysisEligibility(row.analysis_eligibility),
        total_finding_count=row.total_finding_count,
        critical_finding_count=row.critical_finding_count,
        created_at=row.created_at,
        completed_at=row.completed_at,
        failure_code=(
            SanitizationFailureCode(row.failure_code) if row.failure_code is not None else None
        ),
        category_counts=tuple(
            ContentSanitizationCategoryCount(category=item.category, count=item.count)
            for item in category_rows
        ),
    )


def to_row(record: ContentSanitization) -> ContentSanitizationRow:
    return ContentSanitizationRow(
        id=record.id,
        tenant_id=record.tenant_id,
        source_content_id=record.source_content_id,
        sanitized_content_id=record.sanitized_content_id,
        source_resource_type=record.source_resource_type,
        source_resource_id=record.source_resource_id,
        policy_version=record.policy_version,
        detector_version=record.detector_version,
        status=record.status.value,
        analysis_eligibility=record.analysis_eligibility.value,
        total_finding_count=record.total_finding_count,
        critical_finding_count=record.critical_finding_count,
        created_at=record.created_at,
        completed_at=record.completed_at,
        failure_code=record.failure_code.value if record.failure_code is not None else None,
    )


def category_count_to_row(
    *,
    tenant_id: UUID,
    sanitization_id: UUID,
    entry: ContentSanitizationCategoryCount,
) -> ContentSanitizationCategoryCountRow:
    return ContentSanitizationCategoryCountRow(
        sanitization_id=sanitization_id,
        category=entry.category,
        tenant_id=tenant_id,
        count=entry.count,
    )
