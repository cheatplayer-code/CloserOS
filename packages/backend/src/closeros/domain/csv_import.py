"""Framework-independent CSV import domain types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_MAX_MAPPING_FIELDS = 16
_MAX_IDEMPOTENCY_KEY_LENGTH = 128


class CsvImportStatus(StrEnum):
    UPLOADED = "uploaded"
    READY = "ready"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CsvDelimiter(StrEnum):
    COMMA = "comma"
    SEMICOLON = "semicolon"
    TAB = "tab"


class CsvSourceEncoding(StrEnum):
    UTF8 = "utf8"
    UTF8_BOM = "utf8_bom"


class CsvImportErrorCode(StrEnum):
    INVALID_ROW = "invalid_row"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_TIMESTAMP = "invalid_timestamp"
    INVALID_ENUM_VALUE = "invalid_enum_value"
    DUPLICATE_EXTERNAL_MESSAGE = "duplicate_external_message"
    MESSAGE_TOO_LARGE = "message_too_large"
    THREAD_UNAVAILABLE = "thread_unavailable"
    MAPPING_INVALID = "mapping_invalid"


_REQUIRED_MAPPING_FIELDS = frozenset(
    {
        "external_conversation_id",
        "external_message_id",
        "sender_type",
        "direction",
        "sent_at",
        "received_at",
        "message_text",
    }
)

_OPTIONAL_MAPPING_FIELDS = frozenset({"reply_to_external_message_id"})

_ALLOWED_MAPPING_FIELDS = _REQUIRED_MAPPING_FIELDS | _OPTIONAL_MAPPING_FIELDS


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
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")

    if value < 0:
        raise ValueError(f"{field_name} must not be negative")

    return value


def _validate_positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")

    if value < 1:
        raise ValueError(f"{field_name} must be positive")

    return value


def _validate_idempotency_key(value: object | None) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError("idempotency_key must be a string")

    normalized_value = value.strip()

    if not normalized_value:
        raise ValueError("idempotency_key must not be empty")

    if len(normalized_value) > _MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ValueError("idempotency_key exceeds allowed length")

    return normalized_value


@dataclass(frozen=True, slots=True)
class CsvColumnMapping:
    """Maps canonical field names to zero-based CSV column indexes."""

    field_indexes: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.field_indexes, tuple):
            raise TypeError("field_indexes must be a tuple")

        if len(self.field_indexes) > _MAX_MAPPING_FIELDS:
            raise ValueError("mapping exceeds allowed field count")

        seen_fields: set[str] = set()
        seen_indexes: set[int] = set()

        for entry in self.field_indexes:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError("field_indexes must contain (field, index) tuples")

            field_name, column_index = entry

            if not isinstance(field_name, str):
                raise TypeError("mapping field names must be strings")

            if field_name not in _ALLOWED_MAPPING_FIELDS:
                raise ValueError("mapping field is not allowed")

            if field_name in seen_fields:
                raise ValueError("mapping field is duplicated")

            if not isinstance(column_index, int) or column_index < 0:
                raise ValueError("column index must be a non-negative integer")

            seen_fields.add(field_name)
            seen_indexes.add(column_index)

        missing_required = _REQUIRED_MAPPING_FIELDS - seen_fields
        if missing_required:
            raise ValueError("required mapping fields are missing")

    def as_dict(self) -> dict[str, int]:
        return dict(self.field_indexes)

    @classmethod
    def from_dict(cls, values: dict[str, int]) -> CsvColumnMapping:
        return cls(field_indexes=tuple(sorted(values.items())))


@dataclass(frozen=True, slots=True)
class CsvImportBatch:
    id: UUID
    tenant_id: UUID
    channel_connection_id: UUID
    source_content_id: UUID
    creator_user_id: UUID
    status: CsvImportStatus
    delimiter: CsvDelimiter
    source_encoding: CsvSourceEncoding
    lawful_source_confirmed_at: datetime
    mapping: CsvColumnMapping | None
    total_rows: int
    next_row_number: int
    succeeded_count: int
    failed_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime
    version: int
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        _validate_uuid(self.channel_connection_id, "channel_connection_id")
        _validate_uuid(self.source_content_id, "source_content_id")
        _validate_uuid(self.creator_user_id, "creator_user_id")

        if not isinstance(self.status, CsvImportStatus):
            raise TypeError("status must be a CsvImportStatus")

        if not isinstance(self.delimiter, CsvDelimiter):
            raise TypeError("delimiter must be a CsvDelimiter")

        if not isinstance(self.source_encoding, CsvSourceEncoding):
            raise TypeError("source_encoding must be a CsvSourceEncoding")

        object.__setattr__(
            self,
            "lawful_source_confirmed_at",
            _validate_timezone_aware_datetime(
                self.lawful_source_confirmed_at,
                "lawful_source_confirmed_at",
            ),
        )

        if self.mapping is not None and not isinstance(self.mapping, CsvColumnMapping):
            raise TypeError("mapping must be a CsvColumnMapping or None")

        object.__setattr__(
            self, "total_rows", _validate_non_negative_int(self.total_rows, "total_rows")
        )
        object.__setattr__(
            self,
            "next_row_number",
            _validate_positive_int(self.next_row_number, "next_row_number"),
        )
        object.__setattr__(
            self,
            "succeeded_count",
            _validate_non_negative_int(self.succeeded_count, "succeeded_count"),
        )
        object.__setattr__(
            self,
            "failed_count",
            _validate_non_negative_int(self.failed_count, "failed_count"),
        )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
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
            self, "expires_at", _validate_timezone_aware_datetime(self.expires_at, "expires_at")
        )
        if self.expires_at < self.created_at:
            raise ValueError("expires_at must not be earlier than created_at")
        object.__setattr__(self, "version", _validate_positive_int(self.version, "version"))
        object.__setattr__(self, "idempotency_key", _validate_idempotency_key(self.idempotency_key))


@dataclass(frozen=True, slots=True)
class CsvImportRowError:
    import_id: UUID
    row_number: int
    error_code: CsvImportErrorCode
    occurred_at: datetime

    def __post_init__(self) -> None:
        _validate_uuid(self.import_id, "import_id")
        object.__setattr__(
            self, "row_number", _validate_positive_int(self.row_number, "row_number")
        )
        if not isinstance(self.error_code, CsvImportErrorCode):
            raise TypeError("error_code must be a CsvImportErrorCode")
        object.__setattr__(
            self,
            "occurred_at",
            _validate_timezone_aware_datetime(self.occurred_at, "occurred_at"),
        )
