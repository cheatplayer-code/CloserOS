"""Unit tests for deterministic privacy sanitization (Block LM)."""

from __future__ import annotations

from closeros.application.privacy_sanitizer import (
    sanitize_already_sanitized_text,
    sanitize_text,
)
from closeros.domain.privacy_redaction import (
    AnalysisEligibility,
    SanitizationFailureCode,
    SanitizationPolicy,
    SanitizationStatus,
    SensitiveDataCategory,
    placeholder_for_category,
)

SYNTHETIC_EMAIL = "notify@corp.synthetic.invalid"
SYNTHETIC_PHONE = "+7 (900) 000-00-02"
SYNTHETIC_PASSWORD = "password: synth-secret-value"
SYNTHETIC_JWT = "eyJhbGTest00002.abc12345678901.def98765432109"


def test_clean_text_is_not_applicable() -> None:
    raw = b"Synthetic status update with order ref ORD-0002."
    result = sanitize_text(raw_bytes=raw)
    assert result.status is SanitizationStatus.COMPLETED
    assert result.eligibility is AnalysisEligibility.NOT_APPLICABLE
    assert result.failure_code is None
    assert result.sanitized_text == raw.decode("utf-8")
    assert result.summary.total_count == 0
    assert result.post_sanitization_summary.total_count == 0


def test_empty_bytes_is_not_applicable() -> None:
    result = sanitize_text(raw_bytes=b"")
    assert result.eligibility is AnalysisEligibility.NOT_APPLICABLE
    assert result.sanitized_text == ""


def test_email_replaced_with_placeholder() -> None:
    raw = f"Reach {SYNTHETIC_EMAIL} for sandbox.".encode()
    result = sanitize_text(raw_bytes=raw)
    assert result.eligibility is AnalysisEligibility.ELIGIBLE
    assert SYNTHETIC_EMAIL not in result.sanitized_text
    assert placeholder_for_category(SensitiveDataCategory.EMAIL) in result.sanitized_text
    assert result.summary.total_count == 1
    assert result.post_sanitization_summary.total_count == 0


def test_multiple_categories_use_distinct_placeholders() -> None:
    raw = f"Email {SYNTHETIC_EMAIL} phone {SYNTHETIC_PHONE}.".encode()
    result = sanitize_text(raw_bytes=raw)
    assert result.eligibility is AnalysisEligibility.ELIGIBLE
    assert SYNTHETIC_EMAIL not in result.sanitized_text
    assert SYNTHETIC_PHONE not in result.sanitized_text
    assert placeholder_for_category(SensitiveDataCategory.EMAIL) in result.sanitized_text
    assert placeholder_for_category(SensitiveDataCategory.TELEPHONE) in result.sanitized_text
    assert result.summary.total_count == 2


def test_sanitization_is_idempotent() -> None:
    raw = f"Token {SYNTHETIC_JWT} expired.".encode()
    first = sanitize_text(raw_bytes=raw)
    second = sanitize_text(raw_bytes=first.sanitized_text.encode("utf-8"))
    assert first.eligibility is AnalysisEligibility.ELIGIBLE
    assert second.eligibility is AnalysisEligibility.NOT_APPLICABLE
    assert first.sanitized_text == second.sanitized_text


def test_sanitize_already_sanitized_text_accepts_clean_payload() -> None:
    clean = "Synthetic payload without restricted markers."
    result = sanitize_already_sanitized_text(clean)
    assert result.eligibility is AnalysisEligibility.ELIGIBLE
    assert result.sanitized_text == clean
    assert result.summary.total_count == 0


def test_sanitize_already_sanitized_text_blocks_restricted_payload() -> None:
    dirty = f"Still contains {SYNTHETIC_EMAIL}."
    result = sanitize_already_sanitized_text(dirty)
    assert result.eligibility is AnalysisEligibility.BLOCKED
    assert result.failure_code is SanitizationFailureCode.UNRESOLVED_RESTRICTED
    assert result.sanitized_text == ""


def test_blocked_on_invalid_utf8() -> None:
    result = sanitize_text(raw_bytes=b"\xff\xfe synthetic")
    assert result.eligibility is AnalysisEligibility.BLOCKED
    assert result.failure_code is SanitizationFailureCode.INVALID_UTF8
    assert result.sanitized_text == ""


def test_blocked_on_control_content() -> None:
    result = sanitize_text(raw_bytes=b"Synthetic\x07control payload.")
    assert result.eligibility is AnalysisEligibility.BLOCKED
    assert result.failure_code is SanitizationFailureCode.CONTROL_CONTENT
    assert result.sanitized_text == ""


def test_password_assignment_blocks_eligibility() -> None:
    raw = f"Config {SYNTHETIC_PASSWORD} ignored.".encode()
    result = sanitize_text(raw_bytes=raw)
    assert result.eligibility is AnalysisEligibility.ELIGIBLE
    assert SYNTHETIC_PASSWORD not in result.sanitized_text
    assert placeholder_for_category(SensitiveDataCategory.PASSWORD_ASSIGNMENT) in (
        result.sanitized_text
    )
    assert result.post_sanitization_summary.total_count == 0


def test_deterministic_output_for_same_input() -> None:
    raw = f"Email {SYNTHETIC_EMAIL} and phone {SYNTHETIC_PHONE}.".encode()
    first = sanitize_text(raw_bytes=raw)
    second = sanitize_text(raw_bytes=raw)
    assert first.sanitized_text == second.sanitized_text
    assert first.summary.total_count == second.summary.total_count
    assert first.eligibility == second.eligibility


def test_post_sanitization_summary_empty_on_success() -> None:
    raw = f"Contact {SYNTHETIC_EMAIL}.".encode()
    result = sanitize_text(raw_bytes=raw)
    assert result.post_sanitization_summary.total_count == 0
    assert result.post_sanitization_summary.critical_count == 0


def test_critical_count_preserved_in_initial_summary() -> None:
    raw = f"Card 4000 0000 0000 0002 and email {SYNTHETIC_EMAIL}.".encode()
    result = sanitize_text(raw_bytes=raw)
    assert result.summary.critical_count >= 1
    assert result.summary.total_count >= 2


def test_policy_argument_is_accepted() -> None:
    raw = b"Synthetic payload."
    policy = SanitizationPolicy()
    result = sanitize_text(raw_bytes=raw, policy=policy)
    assert result.eligibility is AnalysisEligibility.NOT_APPLICABLE


def test_adjacent_findings_both_replaced_without_gap() -> None:
    raw = f"{SYNTHETIC_EMAIL}{SYNTHETIC_PHONE}".encode()
    result = sanitize_text(raw_bytes=raw)
    assert SYNTHETIC_EMAIL not in result.sanitized_text
    assert SYNTHETIC_PHONE not in result.sanitized_text
    assert result.summary.total_count == 2
    assert result.eligibility is AnalysisEligibility.ELIGIBLE
