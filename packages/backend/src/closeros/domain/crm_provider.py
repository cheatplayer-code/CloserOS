"""CRM provider identifiers.

Bitrix24 is provisional for Block XY.
Documentation review date: 2026-07-12
Sandbox verification: NOT completed
"""

from __future__ import annotations

from enum import StrEnum


class CrmProviderCode(StrEnum):
    BITRIX24 = "bitrix24"


__all__ = ["CrmProviderCode"]
