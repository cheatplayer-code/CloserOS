"""Unit tests for shared persistence foundation utilities."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from closeros.application.persistence_errors import (
    PersistenceError,
    TenantMismatchError,
)
from closeros.infrastructure.cursor_pagination import KeysetCursor, apply_keyset_cursor
from closeros.infrastructure.orm_base import NAMING_CONVENTION, Base
from closeros.infrastructure.persistence_errors import (
    integrity_constraint_name,
    translate_integrity_error,
)
from closeros.infrastructure.utc import require_utc_aware
from sqlalchemy import Column, MetaData, Table, select
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.exc import IntegrityError


def test_naming_convention_defines_all_constraint_kinds() -> None:
    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}


def test_base_metadata_uses_naming_convention() -> None:
    assert Base.metadata.naming_convention is NAMING_CONVENTION


def test_require_utc_aware_accepts_timezone_aware_datetime() -> None:
    value = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    assert require_utc_aware(value) is value


def test_require_utc_aware_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="datetime must be timezone-aware"):
        require_utc_aware(datetime(2026, 7, 12, 10, 0))


def test_keyset_cursor_stores_occurred_at_and_row_id() -> None:
    occurred_at = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    row_id = UUID("00000000-0000-0000-0000-000000000001")
    cursor = KeysetCursor(occurred_at=occurred_at, row_id=row_id)

    assert cursor.occurred_at == occurred_at
    assert cursor.row_id == row_id


def test_apply_keyset_cursor_without_cursor_returns_original_statement() -> None:
    metadata = MetaData()
    events = Table(
        "events",
        metadata,
        Column("occurred_at", TIMESTAMP(timezone=True)),
        Column("id", PGUUID(as_uuid=True)),
    )
    statement = select(events)

    assert (
        apply_keyset_cursor(
            statement,
            occurred_at=events.c.occurred_at,
            row_id=events.c.id,
            cursor=None,
        )
        is statement
    )


def test_apply_keyset_cursor_descending_adds_where_clause() -> None:
    metadata = MetaData()
    events = Table(
        "events",
        metadata,
        Column("occurred_at", TIMESTAMP(timezone=True)),
        Column("id", PGUUID(as_uuid=True)),
    )
    statement = select(events)
    cursor = KeysetCursor(
        occurred_at=datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        row_id=UUID("00000000-0000-0000-0000-000000000001"),
    )

    filtered = apply_keyset_cursor(
        statement,
        occurred_at=events.c.occurred_at,
        row_id=events.c.id,
        cursor=cursor,
        descending=True,
    )

    assert getattr(filtered, "_where_criteria", None)


def test_apply_keyset_cursor_ascending_adds_where_clause() -> None:
    metadata = MetaData()
    events = Table(
        "events",
        metadata,
        Column("occurred_at", TIMESTAMP(timezone=True)),
        Column("id", PGUUID(as_uuid=True)),
    )
    statement = select(events)
    cursor = KeysetCursor(
        occurred_at=datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        row_id=UUID("00000000-0000-0000-0000-000000000001"),
    )

    filtered = apply_keyset_cursor(
        statement,
        occurred_at=events.c.occurred_at,
        row_id=events.c.id,
        cursor=cursor,
        descending=False,
    )

    assert getattr(filtered, "_where_criteria", None)


class _FakeDiagnostics:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _FakeOrig(Exception):
    def __init__(self, constraint_name: str | None) -> None:
        super().__init__(constraint_name or "integrity error")
        self.diag = _FakeDiagnostics(constraint_name)


def test_integrity_constraint_name_reads_postgresql_diagnostics() -> None:
    error = IntegrityError("insert", {}, _FakeOrig("uq_example"))

    assert integrity_constraint_name(error) == "uq_example"


def test_integrity_constraint_name_returns_none_without_diagnostics() -> None:
    error = IntegrityError("insert", {}, Exception("no diagnostics"))

    assert integrity_constraint_name(error) is None


class _MappedError(PersistenceError):
    pass


class _DefaultError(PersistenceError):
    pass


def test_translate_integrity_error_maps_known_constraint() -> None:
    error = IntegrityError("insert", {}, _FakeOrig("uq_example"))

    translated = translate_integrity_error(
        error,
        constraint_errors={"uq_example": _MappedError},
        default=_DefaultError,
        message="mapped failure",
    )

    assert isinstance(translated, _MappedError)
    assert str(translated) == "mapped failure"


def test_translate_integrity_error_falls_back_to_default() -> None:
    error = IntegrityError("insert", {}, _FakeOrig("unknown_constraint"))

    translated = translate_integrity_error(
        error,
        constraint_errors={"uq_example": _MappedError},
        default=_DefaultError,
        message="default failure",
    )

    assert isinstance(translated, _DefaultError)
    assert str(translated) == "default failure"


def test_tenant_mismatch_error_is_persistence_error() -> None:
    assert issubclass(TenantMismatchError, PersistenceError)
