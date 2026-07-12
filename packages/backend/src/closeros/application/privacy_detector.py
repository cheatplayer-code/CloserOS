"""Deterministic local PII and restricted-content detector (stdlib only)."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass

from closeros.domain.privacy_redaction import (
    DETECTOR_VERSION,
    DetectionFinding,
    DetectionSummary,
    SensitiveDataCategory,
    SensitiveDataSeverity,
    severity_for_category,
)

_MAX_TEXT_BYTES = 256 * 1024
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_EMAIL_PATTERN = re.compile(
    r"(?<!\w)"
    r"[\w.%+-]+"
    r"@"
    r"[\w-]+(?:\.[\w-]+){1,8}"
    r"(?!\w)",
    re.UNICODE | re.IGNORECASE,
)

_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?\d[\d\s().-]{8,22}\d)(?!\d)",
)

_CARD_CANDIDATE_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){12,23}\d(?!\d)")

_IBAN_PATTERN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.IGNORECASE)

_KZ_ID_PATTERN = re.compile(r"(?<!\d)\d{12}(?!\d)")

_IPV4_PATTERN = re.compile(
    r"(?<![\d.])"
    r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
    r"(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}"
    r"(?![\d.])"
)

_IPV6_PATTERN = re.compile(
    r"(?<![:\w])"
    r"(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}"
    r"(?![:\w])",
)

_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")

_BEARER_PATTERN = re.compile(
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b",
    re.IGNORECASE,
)

_CREDENTIAL_LABEL_PATTERN = re.compile(
    r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)\s*[:=]\s*\S+"
)

_URL_CREDENTIAL_PATTERN = re.compile(
    r"\b[a-z][a-z0-9+.-]*://[^\s/?#:]+:[^\s/?#@]+@[^\s/?#]+",
    re.IGNORECASE,
)

_KZ_WEIGHTS_PRIMARY = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
_KZ_WEIGHTS_SECONDARY = (3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2)


class PrivacyDetectionError(Exception):
    """Raised when detector input cannot be processed safely."""


@dataclass(frozen=True, slots=True)
class _RawFinding:
    category: SensitiveDataCategory
    start: int
    end: int
    rule_id: str


def normalize_text_for_detection(text: str) -> str:
    """NFC-normalize text before deterministic detection."""
    return unicodedata.normalize("NFC", text)


def decode_text_for_detection(raw_bytes: bytes) -> str:
    if len(raw_bytes) > _MAX_TEXT_BYTES:
        raise PrivacyDetectionError("input exceeds maximum size")
    try:
        return normalize_text_for_detection(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise PrivacyDetectionError("invalid utf-8 input") from error


def detect_sensitive_data(text: str) -> DetectionSummary:
    if len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise PrivacyDetectionError("input exceeds maximum size")
    if _CONTROL_CHAR_PATTERN.search(text):
        finding = _to_finding(
            _RawFinding(
                category=SensitiveDataCategory.CONTROL_CONTENT,
                start=0,
                end=min(len(text), 1) or 1,
                rule_id="control_content",
            )
        )
        return _build_summary((finding,))

    normalized = normalize_text_for_detection(text)
    raw_findings: list[_RawFinding] = []
    raw_findings.extend(_detect_emails(normalized))
    raw_findings.extend(_detect_phones(normalized))
    raw_findings.extend(_detect_payment_cards(normalized))
    raw_findings.extend(_detect_ibans(normalized))
    raw_findings.extend(_detect_kazakhstan_ids(normalized))
    raw_findings.extend(_detect_ip_addresses(normalized))
    raw_findings.extend(_detect_jwts(normalized))
    raw_findings.extend(_detect_bearer_tokens(normalized))
    raw_findings.extend(_detect_credential_assignments(normalized))
    raw_findings.extend(_detect_url_credentials(normalized))

    resolved = _resolve_overlaps(raw_findings)
    findings = tuple(_to_finding(item) for item in resolved)
    return _build_summary(findings)


def _build_summary(findings: tuple[DetectionFinding, ...]) -> DetectionSummary:
    critical_count = sum(
        1 for finding in findings if finding.severity is SensitiveDataSeverity.CRITICAL
    )
    return DetectionSummary(
        findings=findings,
        total_count=len(findings),
        critical_count=critical_count,
    )


def _to_finding(raw: _RawFinding) -> DetectionFinding:
    return DetectionFinding(
        category=raw.category,
        start_offset=raw.start,
        end_offset=raw.end,
        severity=severity_for_category(raw.category),
        rule_id=raw.rule_id,
    )


def _detect_emails(text: str) -> list[_RawFinding]:
    return [
        _RawFinding(
            category=SensitiveDataCategory.EMAIL,
            start=match.start(),
            end=match.end(),
            rule_id="email_basic",
        )
        for match in _EMAIL_PATTERN.finditer(text)
    ]


def _detect_phones(text: str) -> list[_RawFinding]:
    findings: list[_RawFinding] = []
    for match in _PHONE_PATTERN.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 10 <= len(digits) <= 15:
            findings.append(
                _RawFinding(
                    category=SensitiveDataCategory.TELEPHONE,
                    start=match.start(),
                    end=match.end(),
                    rule_id="phone_digit_count",
                )
            )
    return findings


def _detect_payment_cards(text: str) -> list[_RawFinding]:
    findings: list[_RawFinding] = []
    for match in _CARD_CANDIDATE_PATTERN.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            findings.append(
                _RawFinding(
                    category=SensitiveDataCategory.PAYMENT_CARD,
                    start=match.start(),
                    end=match.end(),
                    rule_id="payment_card_luhn",
                )
            )
    return findings


def _detect_ibans(text: str) -> list[_RawFinding]:
    findings: list[_RawFinding] = []
    for match in _IBAN_PATTERN.finditer(text):
        candidate = re.sub(r"\s+", "", match.group(0).upper())
        if 15 <= len(candidate) <= 34 and _iban_valid(candidate):
            findings.append(
                _RawFinding(
                    category=SensitiveDataCategory.IBAN,
                    start=match.start(),
                    end=match.end(),
                    rule_id="iban_mod97",
                )
            )
    return findings


def _detect_kazakhstan_ids(text: str) -> list[_RawFinding]:
    findings: list[_RawFinding] = []
    for match in _KZ_ID_PATTERN.finditer(text):
        digits = match.group(0)
        if _kazakhstan_id_valid(digits):
            findings.append(
                _RawFinding(
                    category=SensitiveDataCategory.NATIONAL_ID,
                    start=match.start(),
                    end=match.end(),
                    rule_id="kz_iin_bin_checksum",
                )
            )
    return findings


def _detect_ip_addresses(text: str) -> list[_RawFinding]:
    findings: list[_RawFinding] = []
    for match in _IPV4_PATTERN.finditer(text):
        candidate = match.group(0)
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        findings.append(
            _RawFinding(
                category=SensitiveDataCategory.IP_ADDRESS,
                start=match.start(),
                end=match.end(),
                rule_id="ipv4_stdlib",
            )
        )
    for match in re.finditer(r"(?<![\w:])[0-9a-fA-F:]{2,39}(?![\w:])", text):
        candidate = match.group(0)
        if ":" not in candidate:
            continue
        try:
            parsed = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if isinstance(parsed, ipaddress.IPv6Address):
            findings.append(
                _RawFinding(
                    category=SensitiveDataCategory.IP_ADDRESS,
                    start=match.start(),
                    end=match.end(),
                    rule_id="ipv6_stdlib",
                )
            )
    return findings


def _detect_jwts(text: str) -> list[_RawFinding]:
    return [
        _RawFinding(
            category=SensitiveDataCategory.JWT,
            start=match.start(),
            end=match.end(),
            rule_id="jwt_three_segment",
        )
        for match in _JWT_PATTERN.finditer(text)
    ]


def _detect_bearer_tokens(text: str) -> list[_RawFinding]:
    return [
        _RawFinding(
            category=SensitiveDataCategory.BEARER_TOKEN,
            start=match.start(),
            end=match.end(),
            rule_id="bearer_prefix",
        )
        for match in _BEARER_PATTERN.finditer(text)
    ]


def _detect_credential_assignments(text: str) -> list[_RawFinding]:
    findings: list[_RawFinding] = []
    for match in _CREDENTIAL_LABEL_PATTERN.finditer(text):
        label = match.group(0).split("=", 1)[0].split(":", 1)[0].lower()
        if "password" in label or "passwd" in label:
            category = SensitiveDataCategory.PASSWORD_ASSIGNMENT
            rule_id = "password_assignment"
        else:
            category = SensitiveDataCategory.API_SECRET
            rule_id = "api_secret_assignment"
        findings.append(
            _RawFinding(
                category=category,
                start=match.start(),
                end=match.end(),
                rule_id=rule_id,
            )
        )
    return findings


def _detect_url_credentials(text: str) -> list[_RawFinding]:
    return [
        _RawFinding(
            category=SensitiveDataCategory.URL_CREDENTIAL,
            start=match.start(),
            end=match.end(),
            rule_id="url_userinfo",
        )
        for match in _URL_CREDENTIAL_PATTERN.finditer(text)
    ]


def _severity_rank(severity: SensitiveDataSeverity) -> int:
    return {
        SensitiveDataSeverity.LOW: 1,
        SensitiveDataSeverity.MEDIUM: 2,
        SensitiveDataSeverity.HIGH: 3,
        SensitiveDataSeverity.CRITICAL: 4,
    }[severity]


def _resolve_overlaps(findings: list[_RawFinding]) -> list[_RawFinding]:
    if not findings:
        return []

    ordered = sorted(
        findings,
        key=lambda item: (
            item.start,
            -(item.end - item.start),
            -_severity_rank(severity_for_category(item.category)),
            item.rule_id,
        ),
    )
    resolved: list[_RawFinding] = []
    for candidate in ordered:
        overlaps = False
        for kept in resolved:
            if candidate.start < kept.end and candidate.end > kept.start:
                overlaps = True
                break
        if not overlaps:
            resolved.append(candidate)
    return sorted(resolved, key=lambda item: (item.start, item.end, item.rule_id))


def _luhn_valid(digits: str) -> bool:
    total = 0
    reverse = digits[::-1]
    for index, char in enumerate(reverse):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _iban_valid(iban: str) -> bool:
    rearranged = iban[4:] + iban[:4]
    converted = "".join(str(int(char, 36)) if char.isalpha() else char for char in rearranged)
    remainder = 0
    for char in converted:
        remainder = (remainder * 10 + int(char)) % 97
    return remainder == 1


def _kazakhstan_id_valid(digits: str) -> bool:
    if len(digits) != 12 or not digits.isdigit():
        return False
    check_digit = int(digits[11])
    for weights in (_KZ_WEIGHTS_PRIMARY, _KZ_WEIGHTS_SECONDARY):
        total = sum(int(digits[index]) * weights[index] for index in range(11))
        remainder = total % 11
        if remainder == 10:
            continue
        return remainder == check_digit
    return False


def detector_version() -> str:
    return DETECTOR_VERSION
