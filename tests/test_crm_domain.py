from __future__ import annotations

import pytest
from closeros.domain.crm_connection import (
    CrmConnection,
    CrmConnectionError,
    CrmConnectionStatus,
)
from closeros.domain.crm_provider import CrmProviderCode

from tests.xy_crm_support import CRM_CONNECTION_ID, NOW, TENANT_ID


def test_crm_connection_hides_secrets_by_reference_only() -> None:
    connection = CrmConnection(
        id=CRM_CONNECTION_ID,
        tenant_id=TENANT_ID,
        provider=CrmProviderCode.BITRIX24,
        portal_domain="Example.Bitrix24.KZ",
        client_id_ref="BITRIX24_CLIENT_ID",
        client_secret_ref="BITRIX24_CLIENT_SECRET",
        access_token_ref=None,
        refresh_token_ref=None,
        status=CrmConnectionStatus.DRAFT,
        created_at=NOW,
        updated_at=NOW,
        last_verified_at=None,
        last_successful_sync_at=None,
        version=1,
    )

    assert connection.portal_domain == "example.bitrix24.kz"
    assert "raw-token" not in repr(connection)


def test_active_crm_connection_requires_access_token_reference() -> None:
    with pytest.raises(CrmConnectionError):
        CrmConnection(
            id=CRM_CONNECTION_ID,
            tenant_id=TENANT_ID,
            provider=CrmProviderCode.BITRIX24,
            portal_domain="example.bitrix24.kz",
            client_id_ref=None,
            client_secret_ref=None,
            access_token_ref=None,
            refresh_token_ref=None,
            status=CrmConnectionStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
            last_verified_at=None,
            last_successful_sync_at=None,
            version=1,
        )
