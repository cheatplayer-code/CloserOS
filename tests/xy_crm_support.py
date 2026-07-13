"""Shared CRM test helpers for Block XY."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")
CRM_CONNECTION_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
CRM_ACCESS_TOKEN_REF = "BITRIX24_ACCESS_TOKEN"
CRM_ACCESS_TOKEN = b"bitrix24-test-access-token-value!!"
