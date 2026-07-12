"""Deterministic privacy sanitization service."""

from __future__ import annotations

from closeros.application.privacy_detector import (
    PrivacyDetectionError,
    decode_text_for_detection,
    detect_sensitive_data,
)
from closeros.domain.privacy_redaction import (
    AnalysisEligibility,
    DetectionSummary,
    SanitizationFailureCode,
    SanitizationPolicy,
    SanitizationResult,
    SanitizationStatus,
    placeholder_for_category,
)


def sanitize_text(
    *,
    raw_bytes: bytes,
    policy: SanitizationPolicy | None = None,
) -> SanitizationResult:
    _ = policy or SanitizationPolicy()
    try:
        text = decode_text_for_detection(raw_bytes)
    except PrivacyDetectionError:
        return _blocked_result(
            sanitized_text="",
            summary=_empty_summary(),
            failure_code=SanitizationFailureCode.INVALID_UTF8,
        )

    try:
        initial_summary = detect_sensitive_data(text)
    except PrivacyDetectionError:
        return _blocked_result(
            sanitized_text="",
            summary=_empty_summary(),
            failure_code=SanitizationFailureCode.CONTROL_CONTENT,
        )

    if any(finding.category.value == "control_content" for finding in initial_summary.findings):
        return _blocked_result(
            sanitized_text="",
            summary=initial_summary,
            failure_code=SanitizationFailureCode.CONTROL_CONTENT,
        )

    sanitized_text = _apply_placeholders(text, initial_summary)
    try:
        post_summary = detect_sensitive_data(sanitized_text)
    except PrivacyDetectionError:
        return _blocked_result(
            sanitized_text="",
            summary=initial_summary,
            failure_code=SanitizationFailureCode.UNRESOLVED_RESTRICTED,
        )

    if post_summary.total_count > 0:
        return _blocked_result(
            sanitized_text="",
            summary=initial_summary,
            post_summary=post_summary,
            failure_code=SanitizationFailureCode.UNRESOLVED_RESTRICTED,
        )

    eligibility = (
        AnalysisEligibility.NOT_APPLICABLE
        if initial_summary.total_count == 0
        else AnalysisEligibility.ELIGIBLE
    )
    return SanitizationResult(
        sanitized_text=sanitized_text,
        summary=initial_summary,
        post_sanitization_summary=post_summary,
        eligibility=eligibility,
        status=SanitizationStatus.COMPLETED,
        failure_code=None,
    )


def sanitize_already_sanitized_text(text: str) -> SanitizationResult:
    summary = detect_sensitive_data(text)
    if summary.total_count > 0:
        return _blocked_result(
            sanitized_text="",
            summary=summary,
            failure_code=SanitizationFailureCode.UNRESOLVED_RESTRICTED,
        )
    return SanitizationResult(
        sanitized_text=text,
        summary=_empty_summary(),
        post_sanitization_summary=_empty_summary(),
        eligibility=AnalysisEligibility.ELIGIBLE,
        status=SanitizationStatus.COMPLETED,
        failure_code=None,
    )


def _apply_placeholders(text: str, summary: DetectionSummary) -> str:
    if not summary.findings:
        return text
    parts: list[str] = []
    cursor = 0
    for finding in summary.findings:
        parts.append(text[cursor : finding.start_offset])
        parts.append(placeholder_for_category(finding.category))
        cursor = finding.end_offset
    parts.append(text[cursor:])
    return "".join(parts)


def _empty_summary() -> DetectionSummary:
    return DetectionSummary(findings=(), total_count=0, critical_count=0)


def _blocked_result(
    *,
    sanitized_text: str,
    summary: DetectionSummary,
    post_summary: DetectionSummary | None = None,
    failure_code: SanitizationFailureCode,
) -> SanitizationResult:
    return SanitizationResult(
        sanitized_text=sanitized_text,
        summary=summary,
        post_sanitization_summary=post_summary or _empty_summary(),
        eligibility=AnalysisEligibility.BLOCKED,
        status=SanitizationStatus.COMPLETED,
        failure_code=failure_code,
    )
