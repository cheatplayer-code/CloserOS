"""Application ports for CRM integrations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.domain.crm_connection import CrmConnection
from closeros.domain.provider_credentials import SecretBytes


class CrmAdapterError(Exception):
    """Base class for safe CRM adapter failures."""


class CrmAdapterUnavailableError(CrmAdapterError):
    """Raised when a CRM provider call fails transiently."""


class CrmAdapterUnauthorizedError(CrmAdapterError):
    """Raised when CRM credentials are invalid or revoked."""


@dataclass(frozen=True, slots=True)
class CrmContactSnapshot:
    external_contact_id: str
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    owner_external_id: str | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class CrmContactWrite:
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    owner_external_id: str | None = None


@dataclass(frozen=True, slots=True)
class CrmDealSnapshot:
    external_deal_id: str
    title: str | None
    owner_external_id: str | None
    stage: str | None
    amount_minor: int | None
    currency: str | None
    outcome: str | None
    reason: str | None
    contact_external_id: str | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class CrmDealWrite:
    title: str | None = None
    owner_external_id: str | None = None
    stage: str | None = None
    amount_minor: int | None = None
    currency: str | None = None
    contact_external_id: str | None = None


@dataclass(frozen=True, slots=True)
class CrmOutcomeApply:
    outcome: str
    stage_id: str | None = None
    reason: str | None = None
    amount_minor: int | None = None
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class CrmSyncPage:
    deals: tuple[CrmDealSnapshot, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class CrmContactSyncPage:
    contacts: tuple[CrmContactSnapshot, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class CrmChangedSyncPage:
    contacts: tuple[CrmContactSnapshot, ...]
    deals: tuple[CrmDealSnapshot, ...]
    next_cursor: str | None


class CrmAdapter(Protocol):
    async def verify_connection(self, *, connection: CrmConnection, access_token: str) -> bool: ...

    async def get_contact(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_contact_id: str,
    ) -> CrmContactSnapshot: ...

    async def add_contact(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        fields: CrmContactWrite,
    ) -> str: ...

    async def update_contact(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_contact_id: str,
        fields: CrmContactWrite,
    ) -> None: ...

    async def list_contacts(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        cursor: str | None,
        updated_since: datetime | None,
    ) -> CrmContactSyncPage: ...

    async def get_deal(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_deal_id: str,
    ) -> CrmDealSnapshot: ...

    async def add_deal(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        fields: CrmDealWrite,
    ) -> str: ...

    async def update_deal(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_deal_id: str,
        fields: CrmDealWrite,
    ) -> None: ...

    async def list_deals(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        cursor: str | None,
        updated_since: datetime | None,
    ) -> CrmSyncPage: ...

    async def list_changed(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        cursor: str | None,
        updated_since: datetime | None,
    ) -> CrmChangedSyncPage: ...

    async def apply_outcome(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_deal_id: str,
        outcome: CrmOutcomeApply,
    ) -> None: ...


class CrmCredentialResolver(Protocol):
    async def resolve_access_token(
        self,
        *,
        tenant_id: UUID,
        crm_connection_id: UUID,
        reference_key: str,
    ) -> SecretBytes | None: ...

    async def resolve_refresh_token(
        self,
        *,
        tenant_id: UUID,
        crm_connection_id: UUID,
        reference_key: str,
    ) -> SecretBytes | None: ...


def crm_field_value_hash(value: str | None) -> str:
    """Return a stable SHA-256 hex digest for conflict comparison."""
    import hashlib

    normalized = "" if value is None else value.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def crm_snapshot_field_value(
    snapshot: CrmDealSnapshot | CrmContactSnapshot,
    *,
    external_field_key: str,
) -> str | None:
    """Resolve a mapped external field key from a CRM snapshot."""
    mapping: Mapping[str, str | None]
    if isinstance(snapshot, CrmDealSnapshot):
        mapping = {
            "TITLE": snapshot.title,
            "STAGE_ID": snapshot.stage,
            "OPPORTUNITY": None
            if snapshot.amount_minor is None
            else str(snapshot.amount_minor / 100),
            "CURRENCY_ID": snapshot.currency,
            "ASSIGNED_BY_ID": snapshot.owner_external_id,
            "CLOSED": snapshot.outcome,
            "CONTACT_ID": snapshot.contact_external_id,
        }
    else:
        mapping = {
            "NAME": snapshot.first_name,
            "LAST_NAME": snapshot.last_name,
            "EMAIL": snapshot.email,
            "PHONE": snapshot.phone,
            "ASSIGNED_BY_ID": snapshot.owner_external_id,
        }
    return mapping.get(external_field_key)


__all__ = [
    "CrmAdapter",
    "CrmAdapterError",
    "CrmAdapterUnauthorizedError",
    "CrmAdapterUnavailableError",
    "CrmChangedSyncPage",
    "CrmContactSnapshot",
    "CrmContactSyncPage",
    "CrmContactWrite",
    "CrmCredentialResolver",
    "CrmDealSnapshot",
    "CrmDealWrite",
    "CrmOutcomeApply",
    "CrmSyncPage",
    "crm_field_value_hash",
    "crm_snapshot_field_value",
]
