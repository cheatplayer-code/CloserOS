"""Stable keyset cursor pagination for chronological tenant-scoped queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, or_


@dataclass(frozen=True, slots=True)
class KeysetCursor:
    occurred_at: datetime
    row_id: UUID


@dataclass(frozen=True, slots=True)
class KeysetPage[T]:
    items: tuple[T, ...]
    next_cursor: KeysetCursor | None


def apply_keyset_cursor(
    statement: Select[Any],
    *,
    occurred_at: ColumnElement[datetime],
    row_id: ColumnElement[UUID],
    cursor: KeysetCursor | None,
    descending: bool = True,
) -> Select[Any]:
    if cursor is None:
        return statement

    if descending:
        return statement.where(
            or_(
                occurred_at < cursor.occurred_at,
                and_(
                    occurred_at == cursor.occurred_at,
                    row_id < cursor.row_id,
                ),
            )
        )

    return statement.where(
        or_(
            occurred_at > cursor.occurred_at,
            and_(
                occurred_at == cursor.occurred_at,
                row_id > cursor.row_id,
            ),
        )
    )
