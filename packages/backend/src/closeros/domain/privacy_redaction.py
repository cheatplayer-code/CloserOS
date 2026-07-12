"""Framework-independent privacy redaction domain model.

Deterministic detection covers high-confidence structured identifiers and
credentials only. Arbitrary human names, postal addresses, medical diagnoses,
and all possible secrets are explicitly out of scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_MAX_TEXT_BYTES = 256 * 1024
_MAX_FINDING_OFFSET = _MAX_TEXT_BYTES

_DETECTOR_VERSION_PATTERN = re.compile(r"^lm-detector-v[0-9]+$")
_POLICY_VERSION_PATTERN = re.compile(r"^lm-policy-v[0-9]+$")
_RULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FAILURE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class SensitiveDataCategory(StrEnum):
    EMAIL = "email"
    TELEPHONE = "telephone"
    PAYMENT_CARD = "payment_card"
    IBAN = "iban"
    NATIONAL_ID = "national_id"
    IP_ADDRESS = "ip_address"
    JWT = "jwt"
    BEARER_TOKEN = "bearer_token"
    API_SECRET = "api_secret"
    URL_CREDENTIAL = "url_credential"
    PASSWORD_ASSIGNMENT = "password_assignment"
    CONTROL_CONTENT = "control_content"


class SensitiveDataSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SanitizationStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisEligibility(StrEnum):
    ELIGIBLE = "eligible"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


class SanitizationFailureCode(StrEnum):
    INVALID_UTF8 = "invalid_utf8"
    CONTROL_CONTENT = "control_content"
    UNRESOLVED_RESTRICTED = "unresolved_restricted"
    UNSUPPORTED_ENCODING = "unsupported_encoding"
    PROCESSING_FAILED = "processing_failed"


DETECTOR_VERSION = "lm-detector-v1"
SANITIZATION_POLICY_VERSION = "lm-policy-v1"

_CATEGORY_SEVERITY: dict[SensitiveDataCategory, SensitiveDataSeverity] = {
    SensitiveDataCategory.EMAIL: SensitiveDataSeverity.HIGH,
    SensitiveDataCategory.TELEPHONE: SensitiveDataSeverity.HIGH,
    SensitiveDataCategory.PAYMENT_CARD: SensitiveDataSeverity.CRITICAL,
    SensitiveDataCategory.IBAN: SensitiveDataSeverity.HIGH,
    SensitiveDataCategory.NATIONAL_ID: SensitiveDataSeverity.CRITICAL,
    SensitiveDataCategory.IP_ADDRESS: SensitiveDataSeverity.MEDIUM,
    SensitiveDataCategory.JWT: SensitiveDataSeverity.CRITICAL,
    SensitiveDataCategory.BEARER_TOKEN: SensitiveDataSeverity.CRITICAL,
    SensitiveDataCategory.API_SECRET: SensitiveDataSeverity.CRITICAL,
    SensitiveDataCategory.URL_CREDENTIAL: SensitiveDataSeverity.HIGH,
    SensitiveDataCategory.PASSWORD_ASSIGNMENT: SensitiveDataSeverity.CRITICAL,
    SensitiveDataCategory.CONTROL_CONTENT: SensitiveDataSeverity.CRITICAL,
}

_CATEGORY_PLACEHOLDER: dict[SensitiveDataCategory, str] = {
    SensitiveDataCategory.EMAIL: "[REDACTED_EMAIL]",
    SensitiveDataCategory.TELEPHONE: "[REDACTED_PHONE]",
    SensitiveDataCategory.PAYMENT_CARD: "[REDACTED_PAYMENT_CARD]",
    SensitiveDataCategory.IBAN: "[REDACTED_IBAN]",
    SensitiveDataCategory.NATIONAL_ID: "[REDACTED_NATIONAL_ID]",
    SensitiveDataCategory.IP_ADDRESS: "[REDACTED_IP]",
    SensitiveDataCategory.JWT: "[REDACTED_CREDENTIAL]",
    SensitiveDataCategory.BEARER_TOKEN: "[REDACTED_CREDENTIAL]",
    SensitiveDataCategory.API_SECRET: "[REDACTED_CREDENTIAL]",
    SensitiveDataCategory.URL_CREDENTIAL: "[REDACTED_CREDENTIAL]",
    SensitiveDataCategory.PASSWORD_ASSIGNMENT: "[REDACTED_CREDENTIAL]",
    SensitiveDataCategory.CONTROL_CONTENT: "[REDACTED_CREDENTIAL]",
}


def severity_for_category(category: SensitiveDataCategory) -> SensitiveDataSeverity:
    return _CATEGORY_SEVERITY[category]


def placeholder_for_category(category: SensitiveDataCategory) -> str:
    return _CATEGORY_PLACEHOLDER[category]


def _validate_offset(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    if value > _MAX_FINDING_OFFSET:
        raise ValueError(f"{field_name} exceeds maximum text size")
    return value


def _validate_version(value: object, field_name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not pattern.fullmatch(normalized):
        raise ValueError(f"{field_name} has invalid format")
    return normalized


@dataclass(frozen=True, slots=True)
class DetectionFinding:
    """Transient finding metadata without matched source text."""

    category: SensitiveDataCategory
    start_offset: int
    end_offset: int
    severity: SensitiveDataSeverity
    rule_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, SensitiveDataCategory):
            raise TypeError("category must be a SensitiveDataCategory")
        if not isinstance(self.severity, SensitiveDataSeverity):
            raise TypeError("severity must be a SensitiveDataSeverity")

        start = _validate_offset(self.start_offset, "start_offset")
        end = _validate_offset(self.end_offset, "end_offset")
        if end <= start:
            raise ValueError("end_offset must be greater than start_offset")

        object.__setattr__(self, "start_offset", start)
        object.__setattr__(self, "end_offset", end)
        object.__setattr__(
            self,
            "rule_id",
            _validate_version(self.rule_id, "rule_id", _RULE_ID_PATTERN),
        )

    def __repr__(self) -> str:
        return (
            "DetectionFinding("
            f"category={self.category.value!r}, "
            f"start_offset={self.start_offset}, "
            f"end_offset={self.end_offset}, "
            f"severity={self.severity.value!r}, "
            f"rule_id={self.rule_id!r})"
        )


@dataclass(frozen=True, slots=True)
class DetectionSummary:
    findings: tuple[DetectionFinding, ...]
    total_count: int
    critical_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.findings, tuple):
            raise TypeError("findings must be a tuple")
        for finding in self.findings:
            if not isinstance(finding, DetectionFinding):
                raise TypeError("findings must contain DetectionFinding values")

        if not isinstance(self.total_count, int) or isinstance(self.total_count, bool):
            raise TypeError("total_count must be an int")
        if self.total_count < 0:
            raise ValueError("total_count must be non-negative")
        if self.total_count != len(self.findings):
            raise ValueError("total_count must match findings length")

        if not isinstance(self.critical_count, int) or isinstance(self.critical_count, bool):
            raise TypeError("critical_count must be an int")
        if self.critical_count < 0:
            raise ValueError("critical_count must be non-negative")
        if self.critical_count > self.total_count:
            raise ValueError("critical_count must not exceed total_count")


@dataclass(frozen=True, slots=True)
class SanitizationPolicy:
    version: str = SANITIZATION_POLICY_VERSION
    detector_version: str = DETECTOR_VERSION
    max_text_bytes: int = _MAX_TEXT_BYTES

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "version",
            _validate_version(self.version, "version", _POLICY_VERSION_PATTERN),
        )
        object.__setattr__(
            self,
            "detector_version",
            _validate_version(self.detector_version, "detector_version", _DETECTOR_VERSION_PATTERN),
        )
        if not isinstance(self.max_text_bytes, int) or isinstance(self.max_text_bytes, bool):
            raise TypeError("max_text_bytes must be an int")
        if self.max_text_bytes <= 0 or self.max_text_bytes > _MAX_TEXT_BYTES:
            raise ValueError("max_text_bytes is out of allowed range")


@dataclass(frozen=True, slots=True)
class SanitizationResult:
    sanitized_text: str
    summary: DetectionSummary
    post_sanitization_summary: DetectionSummary
    eligibility: AnalysisEligibility
    status: SanitizationStatus
    failure_code: SanitizationFailureCode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.sanitized_text, str):
            raise TypeError("sanitized_text must be a str")
        if len(self.sanitized_text.encode("utf-8")) > _MAX_TEXT_BYTES:
            raise ValueError("sanitized_text exceeds maximum size")
        if not isinstance(self.summary, DetectionSummary):
            raise TypeError("summary must be a DetectionSummary")
        if not isinstance(self.post_sanitization_summary, DetectionSummary):
            raise TypeError("post_sanitization_summary must be a DetectionSummary")
        if not isinstance(self.eligibility, AnalysisEligibility):
            raise TypeError("eligibility must be an AnalysisEligibility")
        if not isinstance(self.status, SanitizationStatus):
            raise TypeError("status must be a SanitizationStatus")
        if self.failure_code is not None and not isinstance(
            self.failure_code, SanitizationFailureCode
        ):
            raise TypeError("failure_code must be a SanitizationFailureCode or None")


@dataclass(frozen=True, slots=True)
class ContentSanitizationSource:
    resource_type: str
    resource_id: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("resource_type", self.resource_type),
            ("resource_id", self.resource_id),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a str")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, normalized)


def validate_failure_code(value: object) -> SanitizationFailureCode:
    if isinstance(value, SanitizationFailureCode):
        return value
    if not isinstance(value, str):
        raise TypeError("failure_code must be a string")
    normalized = value.strip()
    if not _FAILURE_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("failure_code has invalid format")
    try:
        return SanitizationFailureCode(normalized)
    except ValueError as error:
        raise ValueError("failure_code is not allowed") from error
