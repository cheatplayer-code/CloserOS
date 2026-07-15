#!/usr/bin/env python3
"""Validate CloserOS staging configuration without printing secret values."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, urlparse
from uuid import UUID

_LOCAL_MARKERS = (
    "localhost",
    "127.0.0.1",
    "closeros_local_only_change_me",
    "closeros_local_redis_only_change_me",
)
_STRONG_SECRET_BYTES = 32
_HEX_KEY_CHARACTERS = 64
_SUPPORTED_DEEPSEEK_MODELS = frozenset({"deepseek-v4-flash", "deepseek-v4-pro"})
_DEPRECATED_DEEPSEEK_MODELS = frozenset({"deepseek-chat", "deepseek-reasoner"})


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class PreflightReport:
    status: str
    checks: tuple[PreflightCheck, ...]

    @property
    def exit_code(self) -> int:
        return 0 if self.status == "passed" else 1


class _Collector:
    def __init__(self) -> None:
        self._checks: list[PreflightCheck] = []

    def passed(self, name: str, detail: str) -> None:
        self._checks.append(PreflightCheck(name=name, status="passed", detail=detail))

    def warning(self, name: str, detail: str) -> None:
        self._checks.append(PreflightCheck(name=name, status="warning", detail=detail))

    def failed(self, name: str, detail: str) -> None:
        self._checks.append(PreflightCheck(name=name, status="failed", detail=detail))

    def report(self) -> PreflightReport:
        status = (
            "failed"
            if any(item.status == "failed" for item in self._checks)
            else "passed"
        )
        return PreflightReport(status=status, checks=tuple(self._checks))


def _value(env: Mapping[str, str], name: str) -> str:
    return env.get(name, "").strip()


def _parse_boolean(raw_value: str, *, name: str) -> bool:
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"{name} must be a strict boolean")


def _public_origin(
    raw_value: str,
    *,
    name: str,
    collector: _Collector,
) -> str | None:
    if not raw_value:
        collector.failed(name, f"{name} is required")
        return None
    parsed = urlparse(raw_value)
    if parsed.scheme != "https" or not parsed.netloc:
        collector.failed(name, f"{name} must be an absolute HTTPS origin")
        return None
    if parsed.username is not None or parsed.password is not None:
        collector.failed(name, f"{name} must not contain credentials")
        return None
    if parsed.query or parsed.fragment:
        collector.failed(name, f"{name} must not contain query or fragment")
        return None
    if parsed.path not in {"", "/"}:
        collector.failed(name, f"{name} must not contain an application path")
        return None
    origin = f"{parsed.scheme}://{parsed.netloc}"
    collector.passed(name, f"{name} is an HTTPS origin")
    return origin


def _validate_secret(
    env: Mapping[str, str],
    *,
    name: str,
    collector: _Collector,
    minimum_bytes: int = _STRONG_SECRET_BYTES,
) -> None:
    value = _value(env, name)
    if not value:
        collector.failed(name, f"{name} is required")
        return
    if len(value.encode("utf-8")) < minimum_bytes:
        collector.failed(name, f"{name} must be at least {minimum_bytes} bytes")
        return
    if any(marker in value for marker in _LOCAL_MARKERS):
        collector.failed(name, f"{name} still uses a local-development placeholder")
        return
    collector.passed(name, f"{name} is present and meets the minimum length")


def _validate_hex_key(
    env: Mapping[str, str],
    *,
    name: str,
    collector: _Collector,
) -> None:
    value = _value(env, name)
    if len(value) != _HEX_KEY_CHARACTERS:
        collector.failed(name, f"{name} must contain exactly 64 hexadecimal characters")
        return
    try:
        decoded = bytes.fromhex(value)
    except ValueError:
        collector.failed(name, f"{name} must contain exactly 64 hexadecimal characters")
        return
    if len(decoded) != 32:
        collector.failed(name, f"{name} must decode to exactly 32 bytes")
        return
    collector.passed(name, f"{name} contains a 32-byte staging-only key")


def _validate_database_url(env: Mapping[str, str], collector: _Collector) -> None:
    raw_value = _value(env, "DATABASE_URL")
    if not raw_value:
        collector.failed("DATABASE_URL", "DATABASE_URL is required")
        return
    if any(marker in raw_value for marker in _LOCAL_MARKERS):
        collector.failed("DATABASE_URL", "DATABASE_URL points at local development")
        return
    parsed = urlparse(raw_value)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        collector.failed(
            "DATABASE_URL",
            "DATABASE_URL must use PostgreSQL with psycopg",
        )
        return
    if not parsed.hostname or not parsed.username or parsed.password is None:
        collector.failed(
            "DATABASE_URL",
            "DATABASE_URL must include host and credentials",
        )
        return
    if not (
        parsed.hostname.endswith(".supabase.co")
        or parsed.hostname.endswith(".pooler.supabase.com")
    ):
        collector.failed(
            "DATABASE_URL",
            "DATABASE_URL must target the staging Supabase project",
        )
        return
    port = parsed.port or 5432
    if port == 6543:
        collector.failed(
            "DATABASE_URL",
            "Supabase transaction-pooler port 6543 is not supported by the current persistent SQLAlchemy runtime; use direct or session mode on port 5432",
        )
        return
    if port != 5432:
        collector.failed(
            "DATABASE_URL",
            "DATABASE_URL must use the direct/session port 5432",
        )
        return
    query = parse_qs(parsed.query)
    sslmode = query.get("sslmode", [""])[0].lower()
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        collector.failed(
            "DATABASE_URL",
            "DATABASE_URL must enforce TLS with sslmode=require or stronger",
        )
        return
    collector.passed(
        "DATABASE_URL",
        "Supabase direct/session connection uses port 5432 with TLS",
    )


def _validate_redis_url(env: Mapping[str, str], collector: _Collector) -> None:
    raw_value = _value(env, "REDIS_URL")
    if not raw_value:
        collector.failed("REDIS_URL", "REDIS_URL is required")
        return
    if any(marker in raw_value for marker in _LOCAL_MARKERS):
        collector.failed("REDIS_URL", "REDIS_URL points at local development")
        return
    parsed = urlparse(raw_value)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        collector.failed(
            "REDIS_URL",
            "REDIS_URL must be a valid redis:// or rediss:// URL",
        )
        return
    if parsed.password is None:
        collector.failed("REDIS_URL", "REDIS_URL must include authentication")
        return
    if parsed.scheme == "redis" and not parsed.hostname.endswith(
        ".railway.internal"
    ):
        collector.failed(
            "REDIS_URL",
            "plaintext redis:// is allowed only on Railway private networking; use rediss:// otherwise",
        )
        return
    detail = (
        "Redis uses Railway private networking with authentication"
        if parsed.scheme == "redis"
        else "Redis uses authenticated TLS"
    )
    collector.passed("REDIS_URL", detail)


def _validate_ai(env: Mapping[str, str], collector: _Collector) -> None:
    try:
        enabled = _parse_boolean(
            _value(env, "AI_EXTERNAL_CALLS_ENABLED"),
            name="AI_EXTERNAL_CALLS_ENABLED",
        )
    except ValueError as error:
        collector.failed("AI_EXTERNAL_CALLS_ENABLED", str(error))
        return

    if not enabled:
        collector.passed(
            "AI_EXTERNAL_CALLS_ENABLED",
            "external AI is disabled for baseline deployment",
        )
        if _value(env, "DEEPSEEK_API_KEY"):
            collector.warning(
                "DEEPSEEK_API_KEY",
                "a DeepSeek key is present while external AI is disabled; keep it sealed and verify the kill-switch drill",
            )
        return

    collector.passed("AI_EXTERNAL_CALLS_ENABLED", "external AI is enabled")
    api_key = _value(env, "DEEPSEEK_API_KEY")
    if not api_key:
        collector.failed(
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_API_KEY is required when external AI is enabled",
        )
    elif len(api_key) < 20:
        collector.failed(
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_API_KEY is unexpectedly short",
        )
    else:
        collector.passed(
            "DEEPSEEK_API_KEY",
            "DeepSeek key is present; value was not printed",
        )

    base_url = _value(env, "DEEPSEEK_BASE_URL")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        collector.failed(
            "DEEPSEEK_BASE_URL",
            "DEEPSEEK_BASE_URL must be an absolute HTTPS URL",
        )
    elif (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        collector.failed(
            "DEEPSEEK_BASE_URL",
            "DEEPSEEK_BASE_URL must not contain credentials, query, or fragment",
        )
    elif parsed.hostname != "api.deepseek.com" or parsed.path not in {"", "/"}:
        collector.failed(
            "DEEPSEEK_BASE_URL",
            "S2 direct-provider sign-off requires https://api.deepseek.com/",
        )
    else:
        collector.passed(
            "DEEPSEEK_BASE_URL",
            "DeepSeek base URL targets the reviewed direct provider endpoint",
        )

    model = _value(env, "DEEPSEEK_MODEL")
    if not model:
        collector.failed(
            "DEEPSEEK_MODEL",
            "DEEPSEEK_MODEL is required when external AI is enabled",
        )
    elif model in _DEPRECATED_DEEPSEEK_MODELS:
        collector.failed(
            "DEEPSEEK_MODEL",
            "deprecated DeepSeek aliases are not accepted for staging sign-off",
        )
    elif model not in _SUPPORTED_DEEPSEEK_MODELS:
        collector.failed(
            "DEEPSEEK_MODEL",
            "model is not in the reviewed staging allow-list",
        )
    else:
        collector.passed(
            "DEEPSEEK_MODEL",
            "DeepSeek model is in the reviewed staging allow-list",
        )


def validate_environment(env: Mapping[str, str]) -> PreflightReport:
    collector = _Collector()

    if _value(env, "APP_ENV") != "staging":
        collector.failed("APP_ENV", "managed staging must use APP_ENV=staging")
    else:
        collector.passed("APP_ENV", "explicit managed staging runtime is selected")

    api_origin = _public_origin(
        _value(env, "STAGING_API_URL"),
        name="STAGING_API_URL",
        collector=collector,
    )
    web_origin = _public_origin(
        _value(env, "STAGING_WEB_URL"),
        name="STAGING_WEB_URL",
        collector=collector,
    )
    public_api_origin = _public_origin(
        _value(env, "NEXT_PUBLIC_API_BASE_URL"),
        name="NEXT_PUBLIC_API_BASE_URL",
        collector=collector,
    )
    if api_origin and public_api_origin:
        if api_origin != public_api_origin:
            collector.failed(
                "NEXT_PUBLIC_API_BASE_URL_MATCH",
                "NEXT_PUBLIC_API_BASE_URL must exactly match STAGING_API_URL",
            )
        else:
            collector.passed(
                "NEXT_PUBLIC_API_BASE_URL_MATCH",
                "frontend API target matches the staging API origin",
            )

    allowed_origins = {
        item.strip().rstrip("/")
        for item in _value(env, "AUTH_ALLOWED_ORIGINS").split(",")
        if item.strip()
    }
    if "*" in allowed_origins:
        collector.failed("AUTH_ALLOWED_ORIGINS", "wildcard origins are forbidden")
    elif web_origin and web_origin not in allowed_origins:
        collector.failed(
            "AUTH_ALLOWED_ORIGINS",
            "staging web origin is not allowed by the API",
        )
    elif web_origin:
        collector.passed(
            "AUTH_ALLOWED_ORIGINS",
            "staging web origin is explicitly allowed",
        )
    else:
        collector.failed("AUTH_ALLOWED_ORIGINS", "AUTH_ALLOWED_ORIGINS is required")

    if api_origin and web_origin and api_origin == web_origin:
        collector.warning(
            "STAGING_ORIGIN_SEPARATION",
            "API and web share one origin; supported, but separate origins are expected for Railway and Vercel",
        )
    elif api_origin and web_origin:
        collector.passed(
            "STAGING_ORIGIN_SEPARATION",
            "API and web use distinct HTTPS origins",
        )

    _validate_database_url(env, collector)
    _validate_redis_url(env, collector)
    _validate_secret(env, name="AUTH_CSRF_SECRET", collector=collector)
    _validate_secret(env, name="AUTH_RATE_LIMIT_SECRET", collector=collector)
    _validate_secret(
        env,
        name="REDIS_RATE_LIMIT_HMAC_SECRET",
        collector=collector,
    )
    _validate_hex_key(
        env,
        name="STAGING_ENCRYPTION_KEY_HEX",
        collector=collector,
    )
    _validate_hex_key(
        env,
        name="STAGING_KNOWLEDGE_SEARCH_KEY_HEX",
        collector=collector,
    )

    key_version = _value(env, "STAGING_ENCRYPTION_KEY_VERSION")
    if not key_version:
        collector.failed(
            "STAGING_ENCRYPTION_KEY_VERSION",
            "STAGING_ENCRYPTION_KEY_VERSION is required",
        )
    elif key_version.startswith("dev-") or key_version.startswith("prod-"):
        collector.failed(
            "STAGING_ENCRYPTION_KEY_VERSION",
            "staging encryption key version must be explicitly staging-scoped",
        )
    else:
        collector.passed(
            "STAGING_ENCRYPTION_KEY_VERSION",
            "staging key version is explicitly configured",
        )

    ingestion_service_id = _value(env, "INGESTION_SERVICE_ID")
    try:
        UUID(ingestion_service_id)
    except ValueError:
        collector.failed(
            "INGESTION_SERVICE_ID",
            "INGESTION_SERVICE_ID must be a UUID",
        )
    else:
        collector.passed(
            "INGESTION_SERVICE_ID",
            "ingestion service identity is configured",
        )

    _validate_ai(env, collector)
    return collector.report()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate staging variables without printing secret values"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = validate_environment(os.environ)
    if args.json:
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        for item in report.checks:
            print(f"[{item.status.upper()}] {item.name}: {item.detail}")
        print(f"staging preflight: {report.status}")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
