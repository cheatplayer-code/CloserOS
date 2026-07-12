"""Development/test no-op CSV content scanner."""

from __future__ import annotations


class NoOpImportContentScanner:
    """Development/test scanner that accepts all CSV bytes without inspection."""

    async def scan_csv_bytes(self, *, content: bytes) -> bool:
        return bool(content)
