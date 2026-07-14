"""Framework-independent product catalog domain (Block V1-2).

Critical commercial facts (price, inventory, delivery, discounts) are owned by
deterministic application code. AI may reference IDs only; it must not invent facts.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

SKU_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
LOCATION_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SOURCE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")

MAX_PRODUCT_NAME_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 4000
MAX_DISPLAY_NAME_LENGTH = 200
MAX_ATTRIBUTE_KEYS = 16
MAX_ATTRIBUTE_KEY_LENGTH = 64
MAX_ATTRIBUTE_VALUE_LENGTH = 128
MAX_SKU_LENGTH = 64
MAX_IMPORT_ROWS = 5_000
MAX_IMPORT_FIELD_LENGTH = 512
MAX_IMPORT_FILE_BYTES = 1_048_576
MAX_SEARCH_RESULTS = 25
DEFAULT_INVENTORY_TTL = timedelta(minutes=5)
DEFAULT_PRICE_TTL = timedelta(hours=24)
DEFAULT_DELIVERY_TTL = timedelta(hours=12)
DEFAULT_PROMOTION_TTL = timedelta(hours=6)
DEFAULT_DESCRIPTION_TTL = timedelta(days=90)


class CatalogEntityStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class FactVerificationStatus(StrEnum):
    LIVE = "live"
    VERIFIED = "verified"
    SYNCED = "synced"
    STALE = "stale"
    UNVERIFIED = "unverified"


class PriceKind(StrEnum):
    LIST = "list"
    SALE = "sale"
    PROMOTIONAL = "promotional"


class CatalogSourceKind(StrEnum):
    MANUAL = "manual"
    CSV_IMPORT = "csv_import"
    SYSTEM_SEED = "system_seed"


class CatalogImportStatus(StrEnum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    VALIDATION_FAILED = "validation_failed"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CommercialActionCode(StrEnum):
    QUOTE_LIST_PRICE = "quote_list_price"
    CONFIRM_AVAILABILITY = "confirm_availability"
    QUOTE_DELIVERY = "quote_delivery"
    OFFER_DISCOUNT = "offer_discount"
    HOLD_INVENTORY = "hold_inventory"
    ESCALATE_TO_HUMAN = "escalate_to_human"


class CatalogImportErrorCode(StrEnum):
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_MONEY = "invalid_money"
    INVALID_CURRENCY = "invalid_currency"
    INVALID_QUANTITY = "invalid_quantity"
    INVALID_SKU = "invalid_sku"
    DUPLICATE_SKU = "duplicate_sku"
    FIELD_TOO_LONG = "field_too_long"
    FORMULA_INJECTION = "formula_injection"
    INVALID_CATEGORY = "invalid_category"
    CROSS_TENANT_SOURCE = "cross_tenant_source"
    ROW_LIMIT_EXCEEDED = "row_limit_exceeded"


_CUSTOMER_VISIBLE_STATUSES = frozenset({CatalogEntityStatus.ACTIVE})
_USABLE_FACT_STATUSES = frozenset(
    {
        FactVerificationStatus.LIVE,
        FactVerificationStatus.VERIFIED,
        FactVerificationStatus.SYNCED,
    }
)
_FORMULA_LEADING = frozenset({"=", "+", "-", "@"})


def normalize_catalog_text(value: str) -> str:
    """NFKC + casefold + collapsed whitespace for multilingual matching."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def is_customer_visible_status(status: CatalogEntityStatus) -> bool:
    return status in _CUSTOMER_VISIBLE_STATUSES


def is_usable_verification_status(status: FactVerificationStatus) -> bool:
    return status in _USABLE_FACT_STATUSES


def reject_formula_leading_field(value: str, *, field_name: str) -> str:
    stripped = value.lstrip()
    if stripped and stripped[0] in _FORMULA_LEADING:
        raise ValueError(f"{field_name} looks like a spreadsheet formula")
    return value


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


def _validate_sku(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not SKU_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must match the controlled SKU pattern")
    return normalized


def _validate_category(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip().casefold()
    if not CATEGORY_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must match the controlled category pattern")
    return normalized


def _validate_currency(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip().upper()
    if not CURRENCY_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must be an ISO 4217 currency code")
    return normalized


def _validate_location(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip().casefold()
    if not LOCATION_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must match the controlled location pattern")
    return normalized


def _validate_source_code(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip().casefold()
    if not SOURCE_CODE_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must match the controlled source_code pattern")
    return normalized


def _validate_bounded_string(
    value: object, field_name: str, *, max_length: int, allow_empty: bool = False
) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} exceeds allowed length")
    return normalized


def _validate_non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _validate_positive_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _validate_attributes(value: object) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError("attributes must be a mapping object")
    if len(value) > MAX_ATTRIBUTE_KEYS:
        raise ValueError("attributes exceed allowed key count")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if type(raw_key) is not str or type(raw_value) is not str:
            raise TypeError("attribute keys and values must be strings")
        key = normalize_catalog_text(raw_key)
        val = reject_formula_leading_field(raw_value.strip(), field_name="attribute")
        if not key or len(key) > MAX_ATTRIBUTE_KEY_LENGTH:
            raise ValueError("attribute key is invalid")
        if not val or len(val) > MAX_ATTRIBUTE_VALUE_LENGTH:
            raise ValueError("attribute value is invalid")
        if "=" in key or "=" in val:
            raise ValueError("attribute values must not contain executable expressions")
        if key in normalized:
            raise ValueError("attribute keys must be unique after normalization")
        normalized[key] = val
    return normalized


@dataclass(frozen=True, slots=True)
class CatalogSource:
    id: UUID
    tenant_id: UUID
    source_code: str
    kind: CatalogSourceKind
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self, "source_code", _validate_source_code(self.source_code, "source_code")
        )
        if not isinstance(self.kind, CatalogSourceKind):
            raise TypeError("kind must be a CatalogSourceKind")
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_timezone_aware_datetime(self.updated_at, "updated_at")
        )


@dataclass(frozen=True, slots=True)
class Product:
    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    name_normalized: str
    category_code: str
    description: str
    status: CatalogEntityStatus
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "sku", _validate_sku(self.sku, "sku"))
        name = _validate_bounded_string(self.name, "name", max_length=MAX_PRODUCT_NAME_LENGTH)
        object.__setattr__(self, "name", name)
        expected = normalize_catalog_text(name)
        if type(self.name_normalized) is not str or self.name_normalized != expected:
            object.__setattr__(self, "name_normalized", expected)
        object.__setattr__(
            self, "category_code", _validate_category(self.category_code, "category_code")
        )
        object.__setattr__(
            self,
            "description",
            _validate_bounded_string(
                self.description, "description", max_length=MAX_DESCRIPTION_LENGTH, allow_empty=True
            ),
        )
        if not isinstance(self.status, CatalogEntityStatus):
            raise TypeError("status must be a CatalogEntityStatus")
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_timezone_aware_datetime(self.updated_at, "updated_at")
        )
        object.__setattr__(self, "version", _validate_positive_int(self.version, "version"))


@dataclass(frozen=True, slots=True)
class ProductVariant:
    id: UUID
    tenant_id: UUID
    product_id: UUID
    sku: str
    display_name: str
    attributes: Mapping[str, str]
    status: CatalogEntityStatus
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "product_id", _validate_uuid(self.product_id, "product_id"))
        object.__setattr__(self, "sku", _validate_sku(self.sku, "sku"))
        object.__setattr__(
            self,
            "display_name",
            _validate_bounded_string(
                self.display_name, "display_name", max_length=MAX_DISPLAY_NAME_LENGTH
            ),
        )
        object.__setattr__(self, "attributes", dict(_validate_attributes(self.attributes)))
        if not isinstance(self.status, CatalogEntityStatus):
            raise TypeError("status must be a CatalogEntityStatus")
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_timezone_aware_datetime(self.updated_at, "updated_at")
        )
        object.__setattr__(self, "version", _validate_positive_int(self.version, "version"))


@dataclass(frozen=True, slots=True)
class ProductPrice:
    id: UUID
    tenant_id: UUID
    variant_id: UUID
    amount_minor: int
    currency: str
    price_kind: PriceKind
    valid_from: datetime
    valid_until: datetime | None
    source_id: UUID
    source_updated_at: datetime
    verification_status: FactVerificationStatus
    checked_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "variant_id", _validate_uuid(self.variant_id, "variant_id"))
        amount = _validate_positive_int(self.amount_minor, "amount_minor")
        object.__setattr__(self, "amount_minor", amount)
        object.__setattr__(self, "currency", _validate_currency(self.currency, "currency"))
        if not isinstance(self.price_kind, PriceKind):
            raise TypeError("price_kind must be a PriceKind")
        valid_from = _validate_timezone_aware_datetime(self.valid_from, "valid_from")
        object.__setattr__(self, "valid_from", valid_from)
        if self.valid_until is not None:
            valid_until = _validate_timezone_aware_datetime(self.valid_until, "valid_until")
            if valid_until <= valid_from:
                raise ValueError("valid_until must be later than valid_from")
            object.__setattr__(self, "valid_until", valid_until)
        object.__setattr__(self, "source_id", _validate_uuid(self.source_id, "source_id"))
        object.__setattr__(
            self,
            "source_updated_at",
            _validate_timezone_aware_datetime(self.source_updated_at, "source_updated_at"),
        )
        if not isinstance(self.verification_status, FactVerificationStatus):
            raise TypeError("verification_status must be a FactVerificationStatus")
        if self.checked_at is not None:
            object.__setattr__(
                self, "checked_at", _validate_timezone_aware_datetime(self.checked_at, "checked_at")
            )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_timezone_aware_datetime(self.updated_at, "updated_at")
        )
        object.__setattr__(self, "version", _validate_positive_int(self.version, "version"))


@dataclass(frozen=True, slots=True)
class InventoryLevel:
    id: UUID
    tenant_id: UUID
    variant_id: UUID
    location_code: str
    available_quantity: int
    reserved_quantity: int
    source_id: UUID
    source_updated_at: datetime
    verification_status: FactVerificationStatus
    checked_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "variant_id", _validate_uuid(self.variant_id, "variant_id"))
        object.__setattr__(
            self, "location_code", _validate_location(self.location_code, "location_code")
        )
        available = _validate_non_negative_int(self.available_quantity, "available_quantity")
        reserved = _validate_non_negative_int(self.reserved_quantity, "reserved_quantity")
        if reserved > available:
            raise ValueError("reserved_quantity must not exceed available_quantity")
        object.__setattr__(self, "available_quantity", available)
        object.__setattr__(self, "reserved_quantity", reserved)
        object.__setattr__(self, "source_id", _validate_uuid(self.source_id, "source_id"))
        object.__setattr__(
            self,
            "source_updated_at",
            _validate_timezone_aware_datetime(self.source_updated_at, "source_updated_at"),
        )
        if not isinstance(self.verification_status, FactVerificationStatus):
            raise TypeError("verification_status must be a FactVerificationStatus")
        if self.checked_at is not None:
            object.__setattr__(
                self, "checked_at", _validate_timezone_aware_datetime(self.checked_at, "checked_at")
            )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_timezone_aware_datetime(self.updated_at, "updated_at")
        )
        object.__setattr__(self, "version", _validate_positive_int(self.version, "version"))


@dataclass(frozen=True, slots=True)
class DeliveryFact:
    id: UUID
    tenant_id: UUID
    variant_id: UUID
    location_code: str
    lead_time_hours: int
    source_id: UUID
    source_updated_at: datetime
    verification_status: FactVerificationStatus
    checked_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "variant_id", _validate_uuid(self.variant_id, "variant_id"))
        object.__setattr__(
            self, "location_code", _validate_location(self.location_code, "location_code")
        )
        object.__setattr__(
            self,
            "lead_time_hours",
            _validate_non_negative_int(self.lead_time_hours, "lead_time_hours"),
        )
        object.__setattr__(self, "source_id", _validate_uuid(self.source_id, "source_id"))
        object.__setattr__(
            self,
            "source_updated_at",
            _validate_timezone_aware_datetime(self.source_updated_at, "source_updated_at"),
        )
        if not isinstance(self.verification_status, FactVerificationStatus):
            raise TypeError("verification_status must be a FactVerificationStatus")
        if self.checked_at is not None:
            object.__setattr__(
                self, "checked_at", _validate_timezone_aware_datetime(self.checked_at, "checked_at")
            )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_timezone_aware_datetime(self.updated_at, "updated_at")
        )
        object.__setattr__(self, "version", _validate_positive_int(self.version, "version"))


@dataclass(frozen=True, slots=True)
class CommercialPolicy:
    id: UUID
    tenant_id: UUID
    allow_discount: bool
    max_discount_basis_points: int
    allow_hold_inventory: bool
    default_currency: str
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        if type(self.allow_discount) is not bool:
            raise TypeError("allow_discount must be a bool")
        if type(self.allow_hold_inventory) is not bool:
            raise TypeError("allow_hold_inventory must be a bool")
        bps = _validate_non_negative_int(
            self.max_discount_basis_points, "max_discount_basis_points"
        )
        if bps > 10_000:
            raise ValueError("max_discount_basis_points must not exceed 10000")
        object.__setattr__(self, "max_discount_basis_points", bps)
        object.__setattr__(
            self, "default_currency", _validate_currency(self.default_currency, "default_currency")
        )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_timezone_aware_datetime(self.updated_at, "updated_at")
        )
        object.__setattr__(self, "version", _validate_positive_int(self.version, "version"))


@dataclass(frozen=True, slots=True)
class CatalogFreshnessPolicy:
    """Tenant-configurable TTLs. Defaults are conservative."""

    id: UUID
    tenant_id: UUID
    inventory_ttl_seconds: int
    price_ttl_seconds: int
    delivery_ttl_seconds: int
    promotion_ttl_seconds: int
    description_ttl_seconds: int
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        for field_name in (
            "inventory_ttl_seconds",
            "price_ttl_seconds",
            "delivery_ttl_seconds",
            "promotion_ttl_seconds",
            "description_ttl_seconds",
        ):
            value = getattr(self, field_name)
            object.__setattr__(self, field_name, _validate_positive_int(value, field_name))
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_timezone_aware_datetime(self.updated_at, "updated_at")
        )
        object.__setattr__(self, "version", _validate_positive_int(self.version, "version"))

    @classmethod
    def conservative_defaults(
        cls, *, id: UUID, tenant_id: UUID, now: datetime
    ) -> CatalogFreshnessPolicy:
        return cls(
            id=id,
            tenant_id=tenant_id,
            inventory_ttl_seconds=int(DEFAULT_INVENTORY_TTL.total_seconds()),
            price_ttl_seconds=int(DEFAULT_PRICE_TTL.total_seconds()),
            delivery_ttl_seconds=int(DEFAULT_DELIVERY_TTL.total_seconds()),
            promotion_ttl_seconds=int(DEFAULT_PROMOTION_TTL.total_seconds()),
            description_ttl_seconds=int(DEFAULT_DESCRIPTION_TTL.total_seconds()),
            created_at=now,
            updated_at=now,
            version=1,
        )


@dataclass(frozen=True, slots=True)
class CatalogImportRun:
    id: UUID
    tenant_id: UUID
    source_id: UUID
    creator_user_id: UUID
    status: CatalogImportStatus
    delimiter: str
    payload_sha256: bytes
    payload_bytes: int
    mapping_json: Mapping[str, str] | None
    total_rows: int
    valid_rows: int
    invalid_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "source_id", _validate_uuid(self.source_id, "source_id"))
        object.__setattr__(
            self, "creator_user_id", _validate_uuid(self.creator_user_id, "creator_user_id")
        )
        if not isinstance(self.status, CatalogImportStatus):
            raise TypeError("status must be a CatalogImportStatus")
        if self.delimiter not in {",", ";", "\t"}:
            raise ValueError("delimiter must be comma, semicolon, or tab")
        if type(self.payload_sha256) is not bytes or len(self.payload_sha256) != 32:
            raise ValueError("payload_sha256 must be 32 bytes")
        object.__setattr__(
            self, "payload_bytes", _validate_non_negative_int(self.payload_bytes, "payload_bytes")
        )
        if self.payload_bytes > MAX_IMPORT_FILE_BYTES:
            raise ValueError("payload_bytes exceeds allowed size")
        for field_name in (
            "total_rows",
            "valid_rows",
            "invalid_rows",
            "created_count",
            "updated_count",
            "skipped_count",
            "failed_count",
        ):
            object.__setattr__(
                self, field_name, _validate_non_negative_int(getattr(self, field_name), field_name)
            )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_timezone_aware_datetime(self.updated_at, "updated_at")
        )
        if self.published_at is not None:
            object.__setattr__(
                self,
                "published_at",
                _validate_timezone_aware_datetime(self.published_at, "published_at"),
            )
        object.__setattr__(self, "version", _validate_positive_int(self.version, "version"))


@dataclass(frozen=True, slots=True)
class CatalogImportRowResult:
    id: UUID
    tenant_id: UUID
    import_run_id: UUID
    row_number: int
    source_row_key: str | None
    is_valid: bool
    error_code: CatalogImportErrorCode | None
    error_message: str | None
    normalized_payload: Mapping[str, object] | None
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self, "import_run_id", _validate_uuid(self.import_run_id, "import_run_id")
        )
        object.__setattr__(
            self, "row_number", _validate_positive_int(self.row_number, "row_number")
        )
        if type(self.is_valid) is not bool:
            raise TypeError("is_valid must be a bool")
        if self.error_code is not None and not isinstance(self.error_code, CatalogImportErrorCode):
            raise TypeError("error_code must be a CatalogImportErrorCode")
        if self.error_message is not None:
            object.__setattr__(
                self,
                "error_message",
                _validate_bounded_string(
                    self.error_message, "error_message", max_length=256, allow_empty=False
                ),
            )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )


@dataclass(frozen=True, slots=True)
class FactProvenance:
    source_id: UUID
    source_updated_at: datetime
    verification_status: FactVerificationStatus
    checked_at: datetime | None
    usable: bool
    valid_until: datetime | None


@dataclass(frozen=True, slots=True)
class CatalogSearchFilters:
    category: str | None = None
    budget_min_minor: int | None = None
    budget_max_minor: int | None = None
    currency: str | None = None
    color: str | None = None
    material: str | None = None
    dimensions: str | None = None
    location: str | None = None
    in_stock_only: bool = False
    product_status: CatalogEntityStatus | None = CatalogEntityStatus.ACTIVE
    variant_status: CatalogEntityStatus | None = CatalogEntityStatus.ACTIVE
    query_text: str | None = None
    limit: int = 10

    def __post_init__(self) -> None:
        if self.category is not None:
            object.__setattr__(self, "category", _validate_category(self.category, "category"))
        if self.currency is not None:
            object.__setattr__(self, "currency", _validate_currency(self.currency, "currency"))
        if self.location is not None:
            object.__setattr__(self, "location", _validate_location(self.location, "location"))
        if self.budget_min_minor is not None:
            object.__setattr__(
                self,
                "budget_min_minor",
                _validate_non_negative_int(self.budget_min_minor, "budget_min_minor"),
            )
        if self.budget_max_minor is not None:
            object.__setattr__(
                self,
                "budget_max_minor",
                _validate_positive_int(self.budget_max_minor, "budget_max_minor"),
            )
        if (
            self.budget_min_minor is not None
            and self.budget_max_minor is not None
            and self.budget_min_minor > self.budget_max_minor
        ):
            raise ValueError("budget_min_minor must not exceed budget_max_minor")
        limit = _validate_positive_int(self.limit, "limit")
        if limit > MAX_SEARCH_RESULTS:
            raise ValueError("limit exceeds allowed search result bound")
        object.__setattr__(self, "limit", limit)


@dataclass(frozen=True, slots=True)
class CatalogSearchHit:
    product_id: UUID
    variant_id: UUID
    product_sku: str
    variant_sku: str
    product_name: str
    variant_display_name: str
    category_code: str
    amount_minor: int
    currency: str
    available_quantity: int
    in_stock: bool
    attributes: Mapping[str, str]
    price_provenance: FactProvenance
    inventory_provenance: FactProvenance
    delivery_status: FactVerificationStatus | None
    delivery_usable: bool


class CatalogDomainError(ValueError):
    """Raised when a catalog domain invariant is violated."""


class CatalogOptimisticLockError(CatalogDomainError):
    """Raised when an optimistic version check fails."""


class CatalogAuthorizationError(PermissionError):
    """Raised when a role is not permitted to mutate catalog facts."""


class CatalogGroundingError(CatalogDomainError):
    """Raised when AI output fails deterministic fact validation."""
