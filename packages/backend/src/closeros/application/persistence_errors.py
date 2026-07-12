"""Shared application-layer persistence error types."""

from __future__ import annotations


class PersistenceError(Exception):
    """Base class for safe persistence failures."""


class TenantMismatchError(PersistenceError):
    """Raised when a row's tenant_id does not match the requested tenant scope."""
