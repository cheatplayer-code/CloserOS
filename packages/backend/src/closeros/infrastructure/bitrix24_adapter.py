"""Bitrix24 CRM adapter using official REST endpoints.

Documentation review date: 2026-07-12
Sandbox verification: NOT completed
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

import httpx

from closeros.application.crm_ports import (
    CrmAdapter,
    CrmAdapterUnauthorizedError,
    CrmAdapterUnavailableError,
    CrmChangedSyncPage,
    CrmContactSnapshot,
    CrmContactSyncPage,
    CrmContactWrite,
    CrmDealSnapshot,
    CrmDealWrite,
    CrmOutcomeApply,
    CrmSyncPage,
)
from closeros.domain.crm_connection import CrmConnection

_DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_PAGE_SIZE = 50
_DOMAIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{0,253}$")
_BLOCKED_HOSTNAMES = frozenset({"localhost", "metadata.google.internal"})


class Bitrix24Adapter(CrmAdapter):
    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def verify_connection(self, *, connection: CrmConnection, access_token: str) -> bool:
        data = await self._request_json(
            connection=connection,
            access_token=access_token,
            method="profile",
            payload={},
        )
        return isinstance(data, Mapping)

    async def get_contact(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_contact_id: str,
    ) -> CrmContactSnapshot:
        data = await self._request_json(
            connection=connection,
            access_token=access_token,
            method="crm.contact.get",
            payload={"id": external_contact_id},
        )
        result = _require_mapping_result(data, "bitrix24 contact get malformed")
        return _parse_contact(result)

    async def add_contact(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        fields: CrmContactWrite,
    ) -> str:
        data = await self._request_json(
            connection=connection,
            access_token=access_token,
            method="crm.contact.add",
            payload={"fields": _contact_write_fields(fields)},
        )
        return _require_created_id(data, "bitrix24 contact add malformed")

    async def update_contact(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_contact_id: str,
        fields: CrmContactWrite,
    ) -> None:
        await self._request_json(
            connection=connection,
            access_token=access_token,
            method="crm.contact.update",
            payload={"id": external_contact_id, "fields": _contact_write_fields(fields)},
        )

    async def list_contacts(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        cursor: str | None,
        updated_since: datetime | None,
    ) -> CrmContactSyncPage:
        payload = _list_payload(
            select=[
                "ID",
                "NAME",
                "LAST_NAME",
                "EMAIL",
                "PHONE",
                "ASSIGNED_BY_ID",
                "DATE_MODIFY",
            ],
            cursor=cursor,
            updated_since=updated_since,
        )
        data = await self._request_json(
            connection=connection,
            access_token=access_token,
            method="crm.contact.list",
            payload=payload,
        )
        result, next_cursor = _require_list_result(data, "bitrix24 contact list malformed")
        contacts = tuple(_parse_contact(item) for item in result if isinstance(item, Mapping))
        return CrmContactSyncPage(contacts=contacts, next_cursor=next_cursor)

    async def get_deal(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_deal_id: str,
    ) -> CrmDealSnapshot:
        data = await self._request_json(
            connection=connection,
            access_token=access_token,
            method="crm.deal.get",
            payload={"id": external_deal_id},
        )
        result = _require_mapping_result(data, "bitrix24 deal get malformed")
        return _parse_deal(result)

    async def add_deal(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        fields: CrmDealWrite,
    ) -> str:
        data = await self._request_json(
            connection=connection,
            access_token=access_token,
            method="crm.deal.add",
            payload={"fields": _deal_write_fields(fields)},
        )
        return _require_created_id(data, "bitrix24 deal add malformed")

    async def update_deal(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_deal_id: str,
        fields: CrmDealWrite,
    ) -> None:
        await self._request_json(
            connection=connection,
            access_token=access_token,
            method="crm.deal.update",
            payload={"id": external_deal_id, "fields": _deal_write_fields(fields)},
        )

    async def list_deals(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        cursor: str | None,
        updated_since: datetime | None,
    ) -> CrmSyncPage:
        payload = _list_payload(
            select=[
                "ID",
                "TITLE",
                "ASSIGNED_BY_ID",
                "STAGE_ID",
                "OPPORTUNITY",
                "CURRENCY_ID",
                "DATE_MODIFY",
                "CLOSED",
                "CONTACT_ID",
            ],
            cursor=cursor,
            updated_since=updated_since,
        )
        data = await self._request_json(
            connection=connection,
            access_token=access_token,
            method="crm.deal.list",
            payload=payload,
        )
        result, next_cursor = _require_list_result(data, "bitrix24 deal list malformed")
        deals = tuple(_parse_deal(item) for item in result if isinstance(item, Mapping))
        return CrmSyncPage(deals=deals, next_cursor=next_cursor)

    async def list_changed(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        cursor: str | None,
        updated_since: datetime | None,
    ) -> CrmChangedSyncPage:
        deal_page = await self.list_deals(
            connection=connection,
            access_token=access_token,
            cursor=cursor,
            updated_since=updated_since,
        )
        contact_page = await self.list_contacts(
            connection=connection,
            access_token=access_token,
            cursor=None,
            updated_since=updated_since,
        )
        return CrmChangedSyncPage(
            contacts=contact_page.contacts,
            deals=deal_page.deals,
            next_cursor=deal_page.next_cursor,
        )

    async def apply_outcome(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        external_deal_id: str,
        outcome: CrmOutcomeApply,
    ) -> None:
        fields: dict[str, object] = {}
        if outcome.stage_id is not None:
            fields["STAGE_ID"] = outcome.stage_id
        if outcome.reason is not None:
            fields["COMMENTS"] = outcome.reason
        if outcome.amount_minor is not None:
            fields["OPPORTUNITY"] = outcome.amount_minor / 100
        if outcome.currency is not None:
            fields["CURRENCY_ID"] = outcome.currency
        normalized_outcome = outcome.outcome.strip().lower()
        if normalized_outcome in {"won", "lost"}:
            fields["CLOSED"] = "Y"
        await self._request_json(
            connection=connection,
            access_token=access_token,
            method="crm.deal.update",
            payload={"id": external_deal_id, "fields": fields},
        )

    async def _request_json(
        self,
        *,
        connection: CrmConnection,
        access_token: str,
        method: str,
        payload: Mapping[str, object],
    ) -> object:
        if connection.portal_domain is None:
            raise CrmAdapterUnavailableError("bitrix24 portal domain unavailable")
        url = _build_rest_url(connection.portal_domain, method)
        headers = {"Authorization": f"Bearer {access_token}"}
        client = self._client
        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT_SECONDS)
            close_client = True
        try:
            response = await client.post(
                url,
                json=cast("dict[str, object]", dict(payload)),
                headers=headers,
            )
        except httpx.HTTPError as error:
            raise CrmAdapterUnavailableError("bitrix24 request failed") from error
        finally:
            if close_client:
                await client.aclose()
        if response.status_code in {401, 403}:
            raise CrmAdapterUnauthorizedError("bitrix24 credentials rejected")
        if response.status_code >= 500 or response.status_code == 429:
            raise CrmAdapterUnavailableError("bitrix24 unavailable")
        if response.status_code >= 400:
            raise CrmAdapterUnavailableError("bitrix24 request rejected")
        try:
            return response.json()
        except ValueError as error:
            raise CrmAdapterUnavailableError("bitrix24 response not json") from error


def validate_portal_domain(portal_domain: str) -> str:
    """Validate a Bitrix24 portal hostname for SSRF-safe outbound requests."""
    normalized = portal_domain.strip().lower()
    if not normalized or not _DOMAIN_PATTERN.fullmatch(normalized):
        raise CrmAdapterUnavailableError("bitrix24 portal domain rejected")
    if "@" in normalized or "/" in normalized or ":" in normalized:
        raise CrmAdapterUnavailableError("bitrix24 portal domain rejected")
    if normalized in _BLOCKED_HOSTNAMES or normalized.endswith(".local"):
        raise CrmAdapterUnavailableError("bitrix24 portal domain rejected")
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        return normalized
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        raise CrmAdapterUnavailableError("bitrix24 portal domain rejected")
    return normalized


def _build_rest_url(portal_domain: str, method: str) -> str:
    safe_domain = validate_portal_domain(portal_domain)
    return f"https://{safe_domain}/rest/{method}.json"


def _list_payload(
    *,
    select: list[str],
    cursor: str | None,
    updated_since: datetime | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "select": select,
        "start": int(cursor) if cursor and cursor.isdigit() else 0,
    }
    if updated_since is not None:
        payload["filter"] = {">DATE_MODIFY": updated_since.isoformat()}
    return payload


def _require_mapping_result(data: object, message: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise CrmAdapterUnavailableError(message)
    result = data.get("result")
    if not isinstance(result, Mapping):
        raise CrmAdapterUnavailableError(message)
    return result


def _require_list_result(
    data: object,
    message: str,
) -> tuple[list[object], str | None]:
    if not isinstance(data, Mapping):
        raise CrmAdapterUnavailableError(message)
    result = data.get("result", [])
    if not isinstance(result, list):
        raise CrmAdapterUnavailableError(message)
    next_cursor = data.get("next")
    return result, None if next_cursor is None else str(next_cursor)


def _require_created_id(data: object, message: str) -> str:
    if not isinstance(data, Mapping):
        raise CrmAdapterUnavailableError(message)
    result = data.get("result")
    if result is None:
        raise CrmAdapterUnavailableError(message)
    return str(result)


def _parse_contact(item: Mapping[str, Any]) -> CrmContactSnapshot:
    updated_at = item.get("DATE_MODIFY")
    return CrmContactSnapshot(
        external_contact_id=str(item.get("ID", "")),
        first_name=_optional_str(item.get("NAME")),
        last_name=_optional_str(item.get("LAST_NAME")),
        email=_optional_str(_first_scalar(item.get("EMAIL"))),
        phone=_optional_str(_first_scalar(item.get("PHONE"))),
        owner_external_id=_optional_str(item.get("ASSIGNED_BY_ID")),
        updated_at=datetime.fromisoformat(updated_at) if isinstance(updated_at, str) else None,
    )


def _parse_deal(item: Mapping[str, Any]) -> CrmDealSnapshot:
    amount_minor = _amount_to_minor(item.get("OPPORTUNITY"))
    updated_at = item.get("DATE_MODIFY")
    return CrmDealSnapshot(
        external_deal_id=str(item.get("ID", "")),
        title=_optional_str(item.get("TITLE")),
        owner_external_id=_optional_str(item.get("ASSIGNED_BY_ID")),
        stage=_optional_str(item.get("STAGE_ID")),
        amount_minor=amount_minor,
        currency=_optional_str(item.get("CURRENCY_ID")),
        outcome=_optional_str(item.get("CLOSED")),
        reason=None,
        contact_external_id=_optional_str(item.get("CONTACT_ID")),
        updated_at=datetime.fromisoformat(updated_at) if isinstance(updated_at, str) else None,
    )


def _contact_write_fields(fields: CrmContactWrite) -> dict[str, object]:
    payload: dict[str, object] = {}
    if fields.first_name is not None:
        payload["NAME"] = fields.first_name
    if fields.last_name is not None:
        payload["LAST_NAME"] = fields.last_name
    if fields.email is not None:
        payload["EMAIL"] = [{"VALUE": fields.email, "VALUE_TYPE": "WORK"}]
    if fields.phone is not None:
        payload["PHONE"] = [{"VALUE": fields.phone, "VALUE_TYPE": "WORK"}]
    if fields.owner_external_id is not None:
        payload["ASSIGNED_BY_ID"] = fields.owner_external_id
    return payload


def _deal_write_fields(fields: CrmDealWrite) -> dict[str, object]:
    payload: dict[str, object] = {}
    if fields.title is not None:
        payload["TITLE"] = fields.title
    if fields.owner_external_id is not None:
        payload["ASSIGNED_BY_ID"] = fields.owner_external_id
    if fields.stage is not None:
        payload["STAGE_ID"] = fields.stage
    if fields.amount_minor is not None:
        payload["OPPORTUNITY"] = fields.amount_minor / 100
    if fields.currency is not None:
        payload["CURRENCY_ID"] = fields.currency
    if fields.contact_external_id is not None:
        payload["CONTACT_ID"] = fields.contact_external_id
    return payload


def _amount_to_minor(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(str(value)) * 100))
    except ValueError:
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_scalar(value: object) -> object:
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, Mapping):
            return first.get("VALUE")
        return first
    return value


__all__ = ["Bitrix24Adapter", "validate_portal_domain"]
