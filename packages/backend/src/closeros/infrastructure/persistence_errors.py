"""Safe persistence exception translation for infrastructure repositories."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.exc import IntegrityError

from closeros.application.persistence_errors import PersistenceError


def integrity_constraint_name(error: IntegrityError) -> str | None:
    diagnostics = getattr(error.orig, "diag", None)
    name = getattr(diagnostics, "constraint_name", None)
    return name if isinstance(name, str) else None


def translate_integrity_error[T: PersistenceError](
    error: IntegrityError,
    *,
    constraint_errors: Mapping[str, type[T]],
    default: type[T],
    message: str,
) -> T:
    name = integrity_constraint_name(error)
    if name is not None:
        error_type = constraint_errors.get(name)
        if error_type is not None:
            return error_type(message)
    return default(message)
