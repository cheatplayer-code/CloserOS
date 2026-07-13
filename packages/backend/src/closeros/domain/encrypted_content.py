"""Framework-independent encrypted content domain types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

GCM_NONCE_SIZE_BYTES = 12
DATA_ENCRYPTION_KEY_SIZE_BYTES = 32
CONTENT_AAD_VERSION = 1
RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES = 256 * 1024
PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES = 1024 * 1024
CSV_IMPORT_MAX_PLAINTEXT_BYTES = 10 * 1024 * 1024
KNOWLEDGE_DOCUMENT_MAX_PLAINTEXT_BYTES = 5 * 1024 * 1024
KNOWLEDGE_CHUNK_MAX_PLAINTEXT_BYTES = 32 * 1024
NOTIFICATION_PAYLOAD_MAX_PLAINTEXT_BYTES = 64 * 1024
MFA_TOTP_SECRET_MAX_PLAINTEXT_BYTES = 64
PROVIDER_MEDIA_BINARY_MAX_PLAINTEXT_BYTES = 100 * 1024 * 1024
MAX_KEY_VERSION_LENGTH = 64


class EncryptedContentKind(StrEnum):
    RAW_MESSAGE = "raw_message"
    SANITIZED_MESSAGE = "sanitized_message"
    PROVIDER_PAYLOAD = "provider_payload"
    OUTBOUND_MESSAGE = "outbound_message"
    CSV_IMPORT = "csv_import"
    KNOWLEDGE_DOCUMENT = "knowledge_document"
    KNOWLEDGE_CHUNK = "knowledge_chunk"
    NOTIFICATION_PAYLOAD = "notification_payload"
    PROVIDER_MEDIA_BINARY = "provider_media_binary"
    MFA_TOTP_SECRET = "mfa_totp_secret"


class ContentEncoding(StrEnum):
    UTF8 = "utf8"
    JSON = "json"
    BINARY = "binary"


class EncryptionAlgorithm(StrEnum):
    AES_256_GCM = "aes_256_gcm"


class ContentAccessPurpose(StrEnum):
    REDACTION = "redaction"
    WEBHOOK_NORMALIZATION = "webhook_normalization"
    OUTBOUND_SEND = "outbound_send"
    WHATSAPP_TEMPLATE_SYNC = "whatsapp_template_sync"
    AI_ANALYSIS = "ai_analysis"
    RETENTION_DELETION = "retention_deletion"
    AUDIT_REVIEW = "audit_review"
    KEY_REWRAP = "key_rewrap"
    CSV_IMPORT_PROCESSING = "csv_import_processing"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    CONVERSATION_REVIEW = "conversation_review"
    NOTIFICATION_DELIVERY = "notification_delivery"
    MEDIA_SCAN = "media_scan"
    MFA_TOTP_VERIFY = "mfa_totp_verify"


class EncryptedContentError(ValueError):
    """Raised when encrypted-content domain validation fails."""


class ContentUnavailableError(EncryptedContentError):
    """Raised when encrypted content cannot be decrypted or unwrapped."""


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


def _validate_exact_byte_length(
    value: object,
    *,
    field_name: str,
    expected_length: int,
) -> bytes:
    if type(value) is not bytes:
        raise TypeError(f"{field_name} must be bytes")

    if len(value) != expected_length:
        raise ValueError(f"{field_name} must contain exactly {expected_length} bytes")

    return value


def _validate_non_empty_bytes(value: object, field_name: str) -> bytes:
    if type(value) is not bytes:
        raise TypeError(f"{field_name} must be bytes")

    if not value:
        raise ValueError(f"{field_name} must not be empty")

    return value


def _validate_key_version(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")

    normalized_value = value.strip()

    if not normalized_value:
        raise ValueError(f"{field_name} must not be empty")

    if len(normalized_value) > MAX_KEY_VERSION_LENGTH:
        raise ValueError(f"{field_name} must not exceed {MAX_KEY_VERSION_LENGTH} characters")

    if not normalized_value.replace("_", "").replace("-", "").isalnum():
        raise ValueError(
            f"{field_name} must contain only letters, digits, underscores, and hyphens"
        )

    if not normalized_value[0].isalnum():
        raise ValueError(f"{field_name} must start with a letter or digit")

    return normalized_value


def _validate_aad_version(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")

    if value < 1:
        raise ValueError(f"{field_name} must be greater than or equal to one")

    return value


def _validate_plaintext_byte_length(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")

    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero")

    return value


def max_plaintext_bytes_for_kind(kind: EncryptedContentKind) -> int:
    if not isinstance(kind, EncryptedContentKind):
        raise TypeError("kind must be an EncryptedContentKind")

    if kind is EncryptedContentKind.PROVIDER_PAYLOAD:
        return PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES

    if kind is EncryptedContentKind.CSV_IMPORT:
        return CSV_IMPORT_MAX_PLAINTEXT_BYTES

    if kind is EncryptedContentKind.KNOWLEDGE_DOCUMENT:
        return KNOWLEDGE_DOCUMENT_MAX_PLAINTEXT_BYTES

    if kind is EncryptedContentKind.KNOWLEDGE_CHUNK:
        return KNOWLEDGE_CHUNK_MAX_PLAINTEXT_BYTES

    if kind is EncryptedContentKind.NOTIFICATION_PAYLOAD:
        return NOTIFICATION_PAYLOAD_MAX_PLAINTEXT_BYTES

    if kind is EncryptedContentKind.MFA_TOTP_SECRET:
        return MFA_TOTP_SECRET_MAX_PLAINTEXT_BYTES

    if kind is EncryptedContentKind.PROVIDER_MEDIA_BINARY:
        return PROVIDER_MEDIA_BINARY_MAX_PLAINTEXT_BYTES

    return RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES


def validate_plaintext_for_kind(*, kind: EncryptedContentKind, plaintext: bytes) -> bytes:
    if not isinstance(kind, EncryptedContentKind):
        raise TypeError("kind must be an EncryptedContentKind")

    if type(plaintext) is not bytes:
        raise TypeError("plaintext must be bytes")

    if not plaintext:
        raise EncryptedContentError("plaintext must not be empty")

    if len(plaintext) > max_plaintext_bytes_for_kind(kind):
        raise EncryptedContentError("plaintext exceeds allowed size limit")

    return plaintext


@dataclass(frozen=True, slots=True)
class WrappedDataKey:
    wrapped_data_key: bytes = field(repr=False)
    key_wrap_nonce: bytes = field(repr=False)
    key_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "wrapped_data_key",
            _validate_non_empty_bytes(self.wrapped_data_key, "wrapped_data_key"),
        )
        object.__setattr__(
            self,
            "key_wrap_nonce",
            _validate_exact_byte_length(
                self.key_wrap_nonce,
                field_name="key_wrap_nonce",
                expected_length=GCM_NONCE_SIZE_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "key_version",
            _validate_key_version(self.key_version, "key_version"),
        )


@dataclass(frozen=True, slots=True)
class EncryptedContent:
    id: UUID
    tenant_id: UUID
    kind: EncryptedContentKind
    encoding: ContentEncoding
    ciphertext: bytes = field(repr=False)
    content_nonce: bytes = field(repr=False)
    wrapped_data_key: bytes = field(repr=False)
    key_wrap_nonce: bytes = field(repr=False)
    algorithm: EncryptionAlgorithm
    key_version: str
    aad_version: int
    plaintext_byte_length: int
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")

        if not isinstance(self.kind, EncryptedContentKind):
            raise TypeError("kind must be an EncryptedContentKind")

        if not isinstance(self.encoding, ContentEncoding):
            raise TypeError("encoding must be a ContentEncoding")

        object.__setattr__(
            self,
            "ciphertext",
            _validate_non_empty_bytes(self.ciphertext, "ciphertext"),
        )
        object.__setattr__(
            self,
            "content_nonce",
            _validate_exact_byte_length(
                self.content_nonce,
                field_name="content_nonce",
                expected_length=GCM_NONCE_SIZE_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "wrapped_data_key",
            _validate_non_empty_bytes(self.wrapped_data_key, "wrapped_data_key"),
        )
        object.__setattr__(
            self,
            "key_wrap_nonce",
            _validate_exact_byte_length(
                self.key_wrap_nonce,
                field_name="key_wrap_nonce",
                expected_length=GCM_NONCE_SIZE_BYTES,
            ),
        )

        if not isinstance(self.algorithm, EncryptionAlgorithm):
            raise TypeError("algorithm must be an EncryptionAlgorithm")

        if self.algorithm is not EncryptionAlgorithm.AES_256_GCM:
            raise ValueError("algorithm must be aes_256_gcm")

        object.__setattr__(
            self,
            "key_version",
            _validate_key_version(self.key_version, "key_version"),
        )
        object.__setattr__(
            self,
            "aad_version",
            _validate_aad_version(self.aad_version, "aad_version"),
        )

        plaintext_byte_length = _validate_plaintext_byte_length(
            self.plaintext_byte_length,
            "plaintext_byte_length",
        )

        if plaintext_byte_length > max_plaintext_bytes_for_kind(self.kind):
            raise ValueError("plaintext_byte_length exceeds allowed size limit")

        object.__setattr__(self, "plaintext_byte_length", plaintext_byte_length)

        created_at = _validate_timezone_aware_datetime(self.created_at, "created_at")
        expires_at = _validate_timezone_aware_datetime(self.expires_at, "expires_at")

        if expires_at < created_at:
            raise ValueError("expires_at must not be earlier than created_at")

        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)


@dataclass(frozen=True, slots=True)
class DecryptedContent:
    kind: EncryptedContentKind
    encoding: ContentEncoding
    plaintext_byte_length: int
    _plaintext: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EncryptedContentKind):
            raise TypeError("kind must be an EncryptedContentKind")

        if not isinstance(self.encoding, ContentEncoding):
            raise TypeError("encoding must be a ContentEncoding")

        plaintext_byte_length = _validate_plaintext_byte_length(
            self.plaintext_byte_length,
            "plaintext_byte_length",
        )

        if type(self._plaintext) is not bytes:
            raise TypeError("_plaintext must be bytes")

        if not self._plaintext:
            raise ValueError("_plaintext must not be empty")

        if len(self._plaintext) != plaintext_byte_length:
            raise ValueError("plaintext_byte_length must match plaintext size")

        if len(self._plaintext) > max_plaintext_bytes_for_kind(self.kind):
            raise ValueError("plaintext exceeds allowed size limit")

        object.__setattr__(self, "plaintext_byte_length", plaintext_byte_length)

    def as_bytes(self) -> bytes:
        return self._plaintext

    def as_utf8_text(self) -> str:
        if self.encoding is not ContentEncoding.UTF8:
            raise EncryptedContentError("encoding does not support utf8 text access")

        try:
            return self._plaintext.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EncryptedContentError("plaintext is not valid utf8") from exc

    def as_json_text(self) -> str:
        if self.encoding is not ContentEncoding.JSON:
            raise EncryptedContentError("encoding does not support json text access")

        try:
            return self._plaintext.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EncryptedContentError("plaintext is not valid utf8 json") from exc
