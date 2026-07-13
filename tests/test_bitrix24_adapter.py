from __future__ import annotations

import asyncio

import httpx
import pytest
from closeros.application.crm_ports import CrmAdapterUnavailableError
from closeros.domain.crm_connection import CrmConnection, CrmConnectionStatus
from closeros.domain.crm_provider import CrmProviderCode
from closeros.infrastructure.bitrix24_adapter import Bitrix24Adapter, validate_portal_domain

from tests.xy_crm_support import CRM_CONNECTION_ID, NOW, TENANT_ID


def _connection(*, portal_domain: str = "example.bitrix24.kz") -> CrmConnection:
    return CrmConnection(
        id=CRM_CONNECTION_ID,
        tenant_id=TENANT_ID,
        provider=CrmProviderCode.BITRIX24,
        portal_domain=portal_domain,
        client_id_ref=None,
        client_secret_ref=None,
        access_token_ref="BITRIX24_ACCESS_TOKEN",
        refresh_token_ref=None,
        status=CrmConnectionStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
        last_verified_at=None,
        last_successful_sync_at=None,
        version=1,
    )


def test_bitrix24_adapter_lists_deals_with_authorization_header() -> None:
    asyncio.run(_run_list_deals_test())


async def _run_list_deals_test() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "example.bitrix24.kz"
        assert request.headers.get("Authorization") == "Bearer token"
        assert "auth" not in str(request.url)
        payload = request.read().decode("utf-8")
        assert "crm.deal.list" in str(request.url)
        assert "select" in payload
        return httpx.Response(
            200,
            json={
                "result": [
                    {
                        "ID": "42",
                        "TITLE": "Pilot",
                        "ASSIGNED_BY_ID": "7",
                        "STAGE_ID": "NEW",
                        "OPPORTUNITY": "123.45",
                        "CURRENCY_ID": "KZT",
                        "DATE_MODIFY": "2026-07-12T12:00:00+00:00",
                        "CLOSED": "N",
                        "CONTACT_ID": "9",
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = Bitrix24Adapter(client=client)

    page = await adapter.list_deals(
        connection=_connection(),
        access_token="token",
        cursor=None,
        updated_since=None,
    )

    assert page.deals[0].external_deal_id == "42"
    assert page.deals[0].title == "Pilot"
    assert page.deals[0].amount_minor == 12345
    await client.aclose()


@pytest.mark.parametrize(
    "portal_domain",
    [
        "127.0.0.1",
        "10.0.0.5",
        "localhost",
        "user@evil.example",
        "example.com/path",
    ],
)
def test_validate_portal_domain_rejects_ssrf_targets(portal_domain: str) -> None:
    with pytest.raises(CrmAdapterUnavailableError):
        validate_portal_domain(portal_domain)
