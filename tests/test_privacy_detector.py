"""Unit tests for deterministic privacy detection (Block LM)."""

from __future__ import annotations

import unicodedata

import pytest
from closeros.application.privacy_detector import (
    PrivacyDetectionError,
    decode_text_for_detection,
    detect_sensitive_data,
    detector_version,
    normalize_text_for_detection,
)
from closeros.domain.privacy_redaction import (
    DETECTOR_VERSION,
    DetectionFinding,
    DetectionSummary,
    SensitiveDataCategory,
    SensitiveDataSeverity,
    severity_for_category,
)

# Synthetic fixtures only — not customer data or production credentials.
SYNTHETIC_EMAIL = "notify@corp.synthetic.invalid"
SYNTHETIC_PHONE = "+7 (900) 000-00-01"
SYNTHETIC_LUHN_CARD = "4000 0000 0000 0002"
SYNTHETIC_IBAN = "DE89370400440532013000"
SYNTHETIC_KZ_ID = "000000000000"
SYNTHETIC_IPV4 = "192.0.2.1"
SYNTHETIC_IPV6 = "2001:db8::1"
SYNTHETIC_JWT = "eyJhbGTest00001.abc12345678901.def98765432109"
SYNTHETIC_BEARER = "Bearer synthtoken0000000001"
SYNTHETIC_PASSWORD = "password: synth-secret-value"
SYNTHETIC_API_KEY = "api_key=synth-api-key-value-001"
SYNTHETIC_URL_SCHEME = "https"
SYNTHETIC_URL_USER = "svc"
SYNTHETIC_URL_PASSWORD = "synthpass"
SYNTHETIC_URL_HOST = "host.synthetic.invalid"
SYNTHETIC_URL_CRED = (
    f"{SYNTHETIC_URL_SCHEME}://"
    f"{SYNTHETIC_URL_USER}:{SYNTHETIC_URL_PASSWORD}"
    f"@{SYNTHETIC_URL_HOST}/path"
)


def _categories_in(summary: DetectionSummary) -> set[SensitiveDataCategory]:
    return {finding.category for finding in summary.findings}


def _findings_for(
    summary: DetectionSummary,
    category: SensitiveDataCategory,
) -> tuple[DetectionFinding, ...]:
    return tuple(finding for finding in summary.findings if finding.category is category)


def test_plain_text_has_no_findings() -> None:
    summary = detect_sensitive_data("Synthetic product update with order ref ORD-0001.")
    assert summary.total_count == 0
    assert summary.critical_count == 0


def test_detects_synthetic_email() -> None:
    text = f"Contact {SYNTHETIC_EMAIL} for sandbox status."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.EMAIL in _categories_in(summary)
    finding = _findings_for(summary, SensitiveDataCategory.EMAIL)[0]
    assert finding.rule_id == "email_basic"
    assert finding.severity is SensitiveDataSeverity.HIGH
    assert text[finding.start_offset : finding.end_offset] == SYNTHETIC_EMAIL


def test_detects_synthetic_telephone() -> None:
    text = f"Callback requested at {SYNTHETIC_PHONE} tomorrow."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.TELEPHONE in _categories_in(summary)
    assert _findings_for(summary, SensitiveDataCategory.TELEPHONE)[0].rule_id == "phone_digit_count"


def test_detects_luhn_valid_payment_card() -> None:
    text = f"Card probe {SYNTHETIC_LUHN_CARD} in sandbox."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.PAYMENT_CARD in _categories_in(summary)
    finding = _findings_for(summary, SensitiveDataCategory.PAYMENT_CARD)[0]
    assert finding.rule_id == "payment_card_luhn"
    assert finding.severity is SensitiveDataSeverity.CRITICAL


def test_rejects_non_luhn_card_candidate() -> None:
    text = "Invalid card candidate 1234 5678 9012 3456 in sandbox."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.PAYMENT_CARD not in _categories_in(summary)


def test_detects_valid_iban() -> None:
    text = f"Transfer ref {SYNTHETIC_IBAN} pending."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.IBAN in _categories_in(summary)
    assert _findings_for(summary, SensitiveDataCategory.IBAN)[0].rule_id == "iban_mod97"


def test_rejects_invalid_iban_checksum() -> None:
    text = "Malformed IBAN GB00NWBK00000000000000 in sandbox."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.IBAN not in _categories_in(summary)


def test_detects_valid_kazakhstan_id() -> None:
    text = f"Registry token {SYNTHETIC_KZ_ID} attached."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.NATIONAL_ID in _categories_in(summary)
    assert (
        _findings_for(summary, SensitiveDataCategory.NATIONAL_ID)[0].rule_id
        == "kz_iin_bin_checksum"
    )


def test_rejects_invalid_kazakhstan_id_checksum() -> None:
    text = "Registry token 000000000001 attached."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.NATIONAL_ID not in _categories_in(summary)


def test_detects_synthetic_ipv4_test_net() -> None:
    text = f"Sandbox host {SYNTHETIC_IPV4} reachable."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.IP_ADDRESS in _categories_in(summary)
    assert _findings_for(summary, SensitiveDataCategory.IP_ADDRESS)[0].rule_id == "ipv4_stdlib"


def test_detects_synthetic_ipv6_documentation() -> None:
    text = f"Sandbox host {SYNTHETIC_IPV6} reachable."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.IP_ADDRESS in _categories_in(summary)
    assert _findings_for(summary, SensitiveDataCategory.IP_ADDRESS)[0].rule_id == "ipv6_stdlib"


def test_detects_jwt_three_segment() -> None:
    text = f"Session header {SYNTHETIC_JWT} expired."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.JWT in _categories_in(summary)
    assert _findings_for(summary, SensitiveDataCategory.JWT)[0].rule_id == "jwt_three_segment"


def test_detects_bearer_token() -> None:
    text = f"Authorization {SYNTHETIC_BEARER} rejected."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.BEARER_TOKEN in _categories_in(summary)
    assert _findings_for(summary, SensitiveDataCategory.BEARER_TOKEN)[0].rule_id == "bearer_prefix"


def test_detects_password_assignment() -> None:
    text = f"Config line {SYNTHETIC_PASSWORD} ignored."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.PASSWORD_ASSIGNMENT in _categories_in(summary)
    assert _findings_for(summary, SensitiveDataCategory.PASSWORD_ASSIGNMENT)[0].rule_id == (
        "password_assignment"
    )


def test_detects_api_secret_assignment() -> None:
    text = f"Config line {SYNTHETIC_API_KEY} ignored."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.API_SECRET in _categories_in(summary)
    assert _findings_for(summary, SensitiveDataCategory.API_SECRET)[0].rule_id == (
        "api_secret_assignment"
    )


def test_detects_url_credential() -> None:
    text = f"Webhook target {SYNTHETIC_URL_CRED} unreachable."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.URL_CREDENTIAL in _categories_in(summary)
    assert _findings_for(summary, SensitiveDataCategory.URL_CREDENTIAL)[0].rule_id == "url_userinfo"


def test_detects_control_characters() -> None:
    text = "Synthetic\x07control payload."
    summary = detect_sensitive_data(text)
    assert summary.total_count == 1
    assert summary.critical_count == 1
    finding = summary.findings[0]
    assert finding.category is SensitiveDataCategory.CONTROL_CONTENT
    assert finding.rule_id == "control_content"


def test_false_positive_short_digit_run_not_phone() -> None:
    text = "Order SKU-123456789 is not a phone number."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.TELEPHONE not in _categories_in(summary)


def test_false_positive_invalid_ipv4_octets() -> None:
    text = "Version string 999.999.999.999 is not a routable address."
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.IP_ADDRESS not in _categories_in(summary)


def test_unicode_nfc_normalization_finds_email() -> None:
    local = "caf\u00e9"
    nfd_email = f"{local}@corp.synthetic.invalid"
    text = unicodedata.normalize("NFD", f"Reach {nfd_email} today.")
    summary = detect_sensitive_data(text)
    assert SensitiveDataCategory.EMAIL in _categories_in(summary)
    assert normalize_text_for_detection(text) == unicodedata.normalize("NFC", text)


def test_oversized_input_raises() -> None:
    oversized = "x" * (256 * 1024 + 1)
    with pytest.raises(PrivacyDetectionError, match="maximum size"):
        detect_sensitive_data(oversized)


def test_invalid_utf8_decode_raises() -> None:
    with pytest.raises(PrivacyDetectionError, match="invalid utf-8"):
        decode_text_for_detection(b"\xff\xfe synthetic")


def test_overlap_resolution_keeps_non_overlapping_findings() -> None:
    text = f"Email {SYNTHETIC_EMAIL} and phone {SYNTHETIC_PHONE}."
    summary = detect_sensitive_data(text)
    assert summary.total_count == 2
    offsets = [(finding.start_offset, finding.end_offset) for finding in summary.findings]
    assert offsets[0][1] <= offsets[1][0] or offsets[1][1] <= offsets[0][0]


def test_detection_finding_repr_hides_matched_text() -> None:
    text = f"Contact {SYNTHETIC_EMAIL}."
    finding = detect_sensitive_data(text).findings[0]
    rendered = repr(finding)
    assert SYNTHETIC_EMAIL not in rendered
    assert "start_offset=" in rendered
    assert finding.category.value in rendered


def test_detection_summary_repr_does_not_embed_source_text() -> None:
    text = f"Contact {SYNTHETIC_EMAIL} and {SYNTHETIC_PHONE}."
    summary = detect_sensitive_data(text)
    rendered = repr(summary)
    assert SYNTHETIC_EMAIL not in rendered
    assert SYNTHETIC_PHONE not in rendered
    assert "total_count=" in rendered


def test_detector_version_constant() -> None:
    assert detector_version() == DETECTOR_VERSION


@pytest.mark.parametrize(
    ("category", "expected_severity"),
    [
        (SensitiveDataCategory.EMAIL, SensitiveDataSeverity.HIGH),
        (SensitiveDataCategory.TELEPHONE, SensitiveDataSeverity.HIGH),
        (SensitiveDataCategory.PAYMENT_CARD, SensitiveDataSeverity.CRITICAL),
        (SensitiveDataCategory.IBAN, SensitiveDataSeverity.HIGH),
        (SensitiveDataCategory.NATIONAL_ID, SensitiveDataSeverity.CRITICAL),
        (SensitiveDataCategory.IP_ADDRESS, SensitiveDataSeverity.MEDIUM),
        (SensitiveDataCategory.JWT, SensitiveDataSeverity.CRITICAL),
        (SensitiveDataCategory.BEARER_TOKEN, SensitiveDataSeverity.CRITICAL),
        (SensitiveDataCategory.API_SECRET, SensitiveDataSeverity.CRITICAL),
        (SensitiveDataCategory.URL_CREDENTIAL, SensitiveDataSeverity.HIGH),
        (SensitiveDataCategory.PASSWORD_ASSIGNMENT, SensitiveDataSeverity.CRITICAL),
        (SensitiveDataCategory.CONTROL_CONTENT, SensitiveDataSeverity.CRITICAL),
    ],
)
def test_severity_for_category(
    category: SensitiveDataCategory,
    expected_severity: SensitiveDataSeverity,
) -> None:
    assert severity_for_category(category) is expected_severity
