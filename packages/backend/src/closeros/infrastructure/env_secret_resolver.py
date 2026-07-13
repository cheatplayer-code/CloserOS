"""Environment-variable secret resolver for staging and local overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass

from closeros.application.secret_ports import SecretResolutionError


@dataclass(frozen=True, slots=True)
class EnvSecretResolver:
    """Resolves ``env:VAR_NAME`` references from process environment."""

    env_prefix: str = "env:"

    async def resolve_secret(self, *, reference: str) -> bytes:
        return self.resolve_secret_sync(reference=reference)

    def resolve_secret_sync(self, *, reference: str) -> bytes:
        if not isinstance(reference, str) or not reference.strip():
            raise SecretResolutionError("secret reference must not be empty")

        normalized = reference.strip()
        if not normalized.startswith(self.env_prefix):
            raise SecretResolutionError("unsupported secret reference format")

        variable_name = normalized[len(self.env_prefix) :].strip()
        if not variable_name:
            raise SecretResolutionError("environment variable name is missing")

        raw_value = os.environ.get(variable_name)
        if raw_value is None or not raw_value:
            raise SecretResolutionError("environment secret is unavailable")

        return raw_value.encode("utf-8")


__all__ = ["EnvSecretResolver"]
