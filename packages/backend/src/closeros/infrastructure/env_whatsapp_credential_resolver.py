"""Environment-backed WhatsApp credential resolver.

Reference keys are treated as environment variable names. Secret values are never
logged.
"""

from __future__ import annotations

import os
from uuid import UUID

from closeros.domain.provider_credentials import SecretBytes


class EnvWhatsAppCredentialResolver:
    def __init__(self, *, environ: dict[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ

    async def resolve_access_token(
        self,
        *,
        tenant_id: UUID,
        whatsapp_connection_id: UUID,
        reference_key: str,
    ) -> SecretBytes | None:
        _ = tenant_id
        _ = whatsapp_connection_id
        return self._resolve(reference_key)

    async def resolve_app_secret(
        self,
        *,
        tenant_id: UUID,
        whatsapp_connection_id: UUID,
        reference_key: str,
    ) -> SecretBytes | None:
        _ = tenant_id
        _ = whatsapp_connection_id
        return self._resolve(reference_key)

    async def resolve_verify_token(
        self,
        *,
        tenant_id: UUID,
        whatsapp_connection_id: UUID,
        reference_key: str,
    ) -> SecretBytes | None:
        _ = tenant_id
        _ = whatsapp_connection_id
        return self._resolve(reference_key)

    def _resolve(self, reference_key: str) -> SecretBytes | None:
        if not reference_key:
            return None
        raw_value = self._environ.get(reference_key)
        if raw_value is None or not raw_value:
            return None
        return SecretBytes(value=raw_value.encode("utf-8"))
