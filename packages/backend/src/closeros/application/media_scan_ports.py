"""Application ports for malware scanning of fetched media."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class MediaScanVerdict(StrEnum):
    CLEAN = "clean"
    INFECTED = "infected"
    SCAN_UNAVAILABLE = "scan_unavailable"


class MediaScanError(Exception):
    """Base class for safe media scan failures."""


@dataclass(frozen=True, slots=True)
class MediaScanResult:
    verdict: MediaScanVerdict
    signature: str | None = None


class MediaScanner(Protocol):
    async def scan_bytes(self, *, content: bytes) -> MediaScanResult: ...

    async def scan_chunks(self, *, chunks: Iterable[bytes]) -> MediaScanResult: ...


__all__ = ["MediaScanError", "MediaScanResult", "MediaScanner", "MediaScanVerdict"]
