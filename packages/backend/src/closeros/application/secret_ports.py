"""Application ports for secret resolution."""

from __future__ import annotations

from typing import Protocol


class SecretResolver(Protocol):
    """Resolves secret material from opaque references without logging values."""

    async def resolve_secret(self, *, reference: str) -> bytes: ...


class SecretResolutionError(Exception):
    """Raised when a secret reference cannot be resolved."""


__all__ = ["SecretResolutionError", "SecretResolver"]
