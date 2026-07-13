"""Validate Meta provider media download URLs before authenticated fetch."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

_ALLOWED_HOST_SUFFIXES: tuple[str, ...] = (
    "lookaside.fbsbx.com",
    "facebook.com",
    "fbcdn.net",
)


class MediaUrlValidationError(ValueError):
    """Raised when a provider media download URL fails safety checks."""


def _host_matches_suffix(hostname: str, suffix: str) -> bool:
    return hostname == suffix or hostname.endswith(f".{suffix}")


def is_allowed_meta_media_host(hostname: str) -> bool:
    normalized = hostname.strip().lower().rstrip(".")
    if not normalized:
        return False
    return any(_host_matches_suffix(normalized, suffix) for suffix in _ALLOWED_HOST_SUFFIXES)


def _is_blocked_ip(hostname: str) -> bool:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_meta_media_download_url(url: object) -> str:
    if type(url) is not str:
        raise TypeError("url must be a string")

    normalized = url.strip()
    if not normalized:
        raise MediaUrlValidationError("url must not be empty")

    parsed = urlparse(normalized)
    if parsed.scheme != "https":
        raise MediaUrlValidationError("url must use https")
    if parsed.username or parsed.password:
        raise MediaUrlValidationError("url must not contain userinfo")
    if parsed.fragment:
        raise MediaUrlValidationError("url must not contain a fragment")
    if not parsed.hostname:
        raise MediaUrlValidationError("url must include a host")

    hostname = parsed.hostname.lower()
    if hostname == "localhost":
        raise MediaUrlValidationError("url host is not allowed")
    if _is_blocked_ip(hostname):
        raise MediaUrlValidationError("url host is not allowed")

    port = parsed.port
    if port is not None and port != 443:
        raise MediaUrlValidationError("url port is not allowed")

    if not is_allowed_meta_media_host(hostname):
        raise MediaUrlValidationError("url host is not allowlisted")

    return normalized


__all__ = [
    "MediaUrlValidationError",
    "is_allowed_meta_media_host",
    "validate_meta_media_download_url",
]
