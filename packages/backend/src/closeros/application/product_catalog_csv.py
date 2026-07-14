"""Bounded streaming CSV import for product catalog (CSV only; XLSX adapter not implemented)."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol
from uuid import UUID, uuid4

from closeros.domain.product_catalog import (
    MAX_IMPORT_FIELD_LENGTH,
    MAX_IMPORT_FILE_BYTES,
    MAX_IMPORT_ROWS,
    CatalogImportErrorCode,
    CatalogImportRowResult,
    reject_formula_leading_field,
)

_MONEY_PATTERN = re.compile(r"^\d+([.,]\d{1,2})?$")
_REQUIRED_FIELDS = frozenset(
    {
        "product_sku",
        "variant_sku",
        "product_name",
        "category_code",
        "amount_minor_or_decimal",
        "currency",
        "available_quantity",
        "location_code",
    }
)
_OPTIONAL_FIELDS = frozenset(
    {
        "display_name",
        "description",
        "color",
        "material",
        "dimensions",
        "lead_time_hours",
        "source_row_key",
    }
)
_ALL_FIELDS = _REQUIRED_FIELDS | _OPTIONAL_FIELDS


class CatalogSpreadsheetParser(Protocol):
    """Optional spreadsheet import port. XLSX is not implemented in Block V1-2."""

    def parse(self, payload: bytes) -> Sequence[Mapping[str, str]]: ...


@dataclass(frozen=True, slots=True)
class CatalogCsvParseResult:
    rows: tuple[CatalogImportRowResult, ...]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    payload_sha256: bytes
    payload_bytes: int


def parse_catalog_money_to_minor(raw: str) -> int:
    """Parse exact money without binary float. Accepts minor units or decimal major."""
    value = raw.strip().replace(" ", "")
    if not value:
        raise ValueError("empty money")
    if value.isdigit():
        amount = int(value)
        if amount < 1:
            raise ValueError("money must be positive")
        return amount
    normalized = value.replace(",", ".")
    if not _MONEY_PATTERN.fullmatch(normalized.replace(".", ".", 1)):
        # allow decimal with dot
        pass
    try:
        decimal_value = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("invalid money") from exc
    if decimal_value <= 0:
        raise ValueError("money must be positive")
    minor = int(decimal_value * 100)
    if Decimal(minor) != decimal_value * 100:
        raise ValueError("money has too many fractional digits")
    return minor


def validate_column_mapping(mapping: Mapping[str, str]) -> dict[str, str]:
    """Map canonical field -> CSV header name."""
    if not mapping:
        raise ValueError("mapping is required")
    normalized = {key.strip(): value.strip() for key, value in mapping.items()}
    missing = _REQUIRED_FIELDS - set(normalized)
    if missing:
        raise ValueError("required mapping fields are missing")
    unknown = set(normalized) - _ALL_FIELDS
    if unknown:
        raise ValueError("mapping contains unknown fields")
    return normalized


def parse_catalog_csv(
    *,
    tenant_id: UUID,
    import_run_id: UUID,
    payload: bytes,
    delimiter: str,
    mapping: Mapping[str, str],
    now: datetime | None = None,
) -> CatalogCsvParseResult:
    if len(payload) > MAX_IMPORT_FILE_BYTES:
        raise ValueError("payload exceeds allowed size")
    if delimiter not in {",", ";", "\t"}:
        raise ValueError("unsupported delimiter")

    digest = hashlib.sha256(payload).digest()
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise ValueError("CSV header row is required")

    field_map = validate_column_mapping(mapping)
    headers = {name.strip() for name in reader.fieldnames}
    for csv_header in field_map.values():
        if csv_header not in headers:
            raise ValueError("mapped CSV column is missing")

    occurred = now or datetime.now(UTC)
    results: list[CatalogImportRowResult] = []
    seen_skus: set[str] = set()
    row_number = 0

    for raw_row in reader:
        row_number += 1
        if row_number > MAX_IMPORT_ROWS:
            results.append(
                CatalogImportRowResult(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    import_run_id=import_run_id,
                    row_number=row_number,
                    source_row_key=None,
                    is_valid=False,
                    error_code=CatalogImportErrorCode.ROW_LIMIT_EXCEEDED,
                    error_message="row_limit_exceeded",
                    normalized_payload=None,
                    created_at=occurred,
                )
            )
            break

        try:
            values = _extract_row(raw_row, field_map)
            product_sku = str(values["product_sku"])
            variant_sku = str(values["variant_sku"])
            if product_sku in seen_skus or variant_sku in seen_skus:
                raise _RowError(CatalogImportErrorCode.DUPLICATE_SKU, "duplicate_sku")
            seen_skus.add(product_sku)
            seen_skus.add(variant_sku)
            source_row_key = values.get("source_row_key")
            results.append(
                CatalogImportRowResult(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    import_run_id=import_run_id,
                    row_number=row_number,
                    source_row_key=str(source_row_key) if source_row_key is not None else None,
                    is_valid=True,
                    error_code=None,
                    error_message=None,
                    normalized_payload=values,
                    created_at=occurred,
                )
            )
        except _RowError as exc:
            results.append(
                CatalogImportRowResult(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    import_run_id=import_run_id,
                    row_number=row_number,
                    source_row_key=None,
                    is_valid=False,
                    error_code=exc.code,
                    error_message=exc.message,
                    normalized_payload=None,
                    created_at=occurred,
                )
            )

    valid = sum(1 for item in results if item.is_valid)
    invalid = len(results) - valid
    return CatalogCsvParseResult(
        rows=tuple(results),
        total_rows=len(results),
        valid_rows=valid,
        invalid_rows=invalid,
        payload_sha256=digest,
        payload_bytes=len(payload),
    )


class _RowError(Exception):
    def __init__(self, code: CatalogImportErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _extract_row(
    raw_row: Mapping[str, str | None], field_map: Mapping[str, str]
) -> dict[str, object]:
    def cell(field: str) -> str:
        header = field_map[field]
        value = (raw_row.get(header) or "").strip()
        if len(value) > MAX_IMPORT_FIELD_LENGTH:
            raise _RowError(CatalogImportErrorCode.FIELD_TOO_LONG, "field_too_long")
        try:
            reject_formula_leading_field(value, field_name=field)
        except ValueError as exc:
            raise _RowError(CatalogImportErrorCode.FORMULA_INJECTION, "formula_injection") from exc
        return value

    values: dict[str, object] = {}
    for field in _REQUIRED_FIELDS:
        value = cell(field)
        if not value:
            raise _RowError(CatalogImportErrorCode.MISSING_REQUIRED_FIELD, field)
        values[field] = value

    for field in _OPTIONAL_FIELDS:
        if field not in field_map:
            continue
        value = cell(field)
        if value:
            values[field] = value

    money_raw = str(values["amount_minor_or_decimal"])
    try:
        values["amount_minor"] = parse_catalog_money_to_minor(money_raw)
    except ValueError as exc:
        raise _RowError(CatalogImportErrorCode.INVALID_MONEY, "invalid_money") from exc

    currency = str(values["currency"]).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise _RowError(CatalogImportErrorCode.INVALID_CURRENCY, "invalid_currency")
    values["currency"] = currency

    try:
        qty = int(str(values["available_quantity"]))
        if qty < 0:
            raise ValueError("negative")
    except ValueError as exc:
        raise _RowError(CatalogImportErrorCode.INVALID_QUANTITY, "invalid_quantity") from exc
    values["available_quantity"] = qty

    category = str(values["category_code"]).casefold()
    if not re.fullmatch(r"^[a-z][a-z0-9_-]{0,63}$", category):
        raise _RowError(CatalogImportErrorCode.INVALID_CATEGORY, "invalid_category")
    values["category_code"] = category

    for sku_field in ("product_sku", "variant_sku"):
        sku = str(values[sku_field])
        if not re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", sku):
            raise _RowError(CatalogImportErrorCode.INVALID_SKU, "invalid_sku")

    if "lead_time_hours" in values:
        try:
            lead = int(str(values["lead_time_hours"]))
            if lead < 0:
                raise ValueError("negative")
            values["lead_time_hours"] = lead
        except ValueError as exc:
            raise _RowError(CatalogImportErrorCode.INVALID_QUANTITY, "invalid_lead_time") from exc

    return values
