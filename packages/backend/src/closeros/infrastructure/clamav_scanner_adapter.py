"""ClamAV INSTREAM scanner adapter with mockable transport."""

from __future__ import annotations

import asyncio
import socket
import struct
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from closeros.application.media_scan_ports import MediaScanResult, MediaScanVerdict

_INSTREAM_CHUNK_SIZE_BYTES = 64 * 1024
_MAX_SCANNER_RESPONSE_BYTES = 4096


class ClamAvScanError(Exception):
    """Raised when ClamAV scanning fails."""


def _iter_bounded_frames(chunks: Iterable[bytes]) -> Iterator[bytes]:
    for chunk in chunks:
        if not chunk:
            continue
        for offset in range(0, len(chunk), _INSTREAM_CHUNK_SIZE_BYTES):
            yield chunk[offset : offset + _INSTREAM_CHUNK_SIZE_BYTES]


def _send_instream_frames(
    *,
    host: str,
    port: int,
    timeout_seconds: float,
    frames: Iterable[bytes],
) -> str:
    payload = b"zINSTREAM\0"
    with socket.create_connection((host, port), timeout=timeout_seconds) as sock:
        sock.settimeout(timeout_seconds)
        sock.sendall(payload)
        for part in frames:
            sock.sendall(struct.pack(">I", len(part)))
            sock.sendall(part)
        sock.sendall(struct.pack(">I", 0))
        response_chunks: list[bytes] = []
        total = 0
        while True:
            part = sock.recv(4096)
            if not part:
                break
            total += len(part)
            if total > _MAX_SCANNER_RESPONSE_BYTES:
                raise ClamAvScanError("clamav response exceeds limit")
            response_chunks.append(part)
    return b"".join(response_chunks).decode("utf-8", errors="replace")


@dataclass(frozen=True, slots=True)
class ClamAvScannerAdapter:
    host: str = "127.0.0.1"
    port: int = 3310
    timeout_seconds: float = 30.0

    async def scan_bytes(self, *, content: bytes) -> MediaScanResult:
        if type(content) is not bytes:
            raise TypeError("content must be bytes")
        if not content:
            return MediaScanResult(verdict=MediaScanVerdict.CLEAN)
        return await self.scan_chunks(chunks=(content,))

    async def scan_chunks(self, *, chunks: Iterable[bytes]) -> MediaScanResult:
        frame_iter = _iter_bounded_frames(chunks)

        def _blocking() -> str:
            return _send_instream_frames(
                host=self.host,
                port=self.port,
                timeout_seconds=self.timeout_seconds,
                frames=frame_iter,
            )

        try:
            response = await asyncio.to_thread(_blocking)
        except OSError:
            return MediaScanResult(verdict=MediaScanVerdict.SCAN_UNAVAILABLE)
        except ClamAvScanError:
            return MediaScanResult(verdict=MediaScanVerdict.SCAN_UNAVAILABLE)

        normalized = response.strip()
        if not normalized:
            return MediaScanResult(verdict=MediaScanVerdict.SCAN_UNAVAILABLE)
        if normalized.endswith("OK"):
            return MediaScanResult(verdict=MediaScanVerdict.CLEAN)
        if "FOUND" in normalized:
            signature = normalized.split("FOUND", maxsplit=1)[0].strip().split()[-1]
            return MediaScanResult(verdict=MediaScanVerdict.INFECTED, signature=signature)
        return MediaScanResult(verdict=MediaScanVerdict.SCAN_UNAVAILABLE)


class MockClamAvScannerAdapter:
    """Deterministic scanner for tests without a live ClamAV daemon."""

    def __init__(self, *, verdict: MediaScanVerdict, signature: str | None = None) -> None:
        self._verdict = verdict
        self._signature = signature

    async def scan_bytes(self, *, content: bytes) -> MediaScanResult:
        return await self.scan_chunks(chunks=(content,))

    async def scan_chunks(self, *, chunks: Iterable[bytes]) -> MediaScanResult:
        _ = list(chunks)
        return MediaScanResult(verdict=self._verdict, signature=self._signature)


__all__ = [
    "ClamAvScanError",
    "ClamAvScannerAdapter",
    "MockClamAvScannerAdapter",
]
