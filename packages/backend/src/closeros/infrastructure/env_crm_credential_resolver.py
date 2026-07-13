"""Environment-backed CRM credential resolver for local development/tests."""

from __future__ import annotations

import os
from uuid import UUID

from closeros.application.crm_ports import CrmCredentialResolver
from closeros.domain.provider_credentials import SecretBytes


class EnvCrmCredentialResolver(CrmCredentialResolver):
    async def resolve_access_token(
        self,
        *,
        tenant_id: UUID,
        crm_connection_id: UUID,
        reference_key: str,
    ) -> SecretBytes | None:
        _ = tenant_id, crm_connection_id
        value = os.environ.get(reference_key)
        return None if value is None else SecretBytes(value.encode("utf-8"))

    async def resolve_refresh_token(
        self,
        *,
        tenant_id: UUID,
        crm_connection_id: UUID,
        reference_key: str,
    ) -> SecretBytes | None:
        _ = tenant_id, crm_connection_id
        value = os.environ.get(reference_key)
        return None if value is None else SecretBytes(value.encode("utf-8"))


__all__ = ["EnvCrmCredentialResolver"]
