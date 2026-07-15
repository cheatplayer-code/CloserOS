"""Unit tests for the S2 staging configuration preflight."""

from __future__ import annotations

from scripts.ops.staging_preflight import validate_environment


def _base_environment() -> dict[str, str]:
    return {
        "APP_ENV": "staging",
        "STAGING_API_URL": "https://api-staging.example.com",
        "STAGING_WEB_URL": "https://web-staging.example.com",
        "NEXT_PUBLIC_API_BASE_URL": "https://api-staging.example.com",
        "AUTH_ALLOWED_ORIGINS": "https://web-staging.example.com",
        "DATABASE_URL": (
            "postgresql+psycopg://postgres.project:staging-db-password@"
            "aws-0-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require"
        ),
        "REDIS_URL": ("redis://default:staging-redis-password@redis.railway.internal:6379/0"),
        "REDIS_RATE_LIMIT_HMAC_SECRET": "h" * 48,
        "AUTH_CSRF_SECRET": "c" * 48,
        "AUTH_RATE_LIMIT_SECRET": "r" * 48,
        "STAGING_ENCRYPTION_KEY_HEX": "11" * 32,
        "STAGING_ENCRYPTION_KEY_VERSION": "staging-kek-v1",
        "STAGING_KNOWLEDGE_SEARCH_KEY_HEX": "22" * 32,
        "INGESTION_SERVICE_ID": "7f53206e-9b57-49cc-9f79-3c3f3a750dfa",
        "AI_EXTERNAL_CALLS_ENABLED": "false",
        "DEEPSEEK_API_KEY": "",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com/",
        "DEEPSEEK_MODEL": "deepseek-v4-flash",
    }


def _failed_names(environment: dict[str, str]) -> set[str]:
    report = validate_environment(environment)
    return {item.name for item in report.checks if item.status == "failed"}


def test_valid_disabled_staging_configuration_passes() -> None:
    report = validate_environment(_base_environment())

    assert report.status == "passed"
    assert report.exit_code == 0
    assert not [item for item in report.checks if item.status == "failed"]


def test_valid_enabled_deepseek_configuration_passes_without_exposing_key() -> None:
    environment = _base_environment()
    secret = "sk-staging-secret-that-must-never-appear-in-output"
    environment.update(
        {
            "AI_EXTERNAL_CALLS_ENABLED": "true",
            "DEEPSEEK_API_KEY": secret,
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
        }
    )

    report = validate_environment(environment)

    assert report.status == "passed"
    assert secret not in repr(report)


def test_transaction_pooler_is_rejected_for_persistent_runtime() -> None:
    environment = _base_environment()
    environment["DATABASE_URL"] = (
        "postgresql+psycopg://postgres.project:staging-db-password@"
        "aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require"
    )

    assert "DATABASE_URL" in _failed_names(environment)


def test_public_redis_requires_tls() -> None:
    environment = _base_environment()
    environment["REDIS_URL"] = "redis://default:secret@redis-public.example.com:6379/0"

    assert "REDIS_URL" in _failed_names(environment)


def test_invalid_staging_hex_keys_are_rejected() -> None:
    environment = _base_environment()
    environment["STAGING_ENCRYPTION_KEY_HEX"] = "not-hex"
    environment["STAGING_KNOWLEDGE_SEARCH_KEY_HEX"] = "33" * 31

    failed = _failed_names(environment)

    assert "STAGING_ENCRYPTION_KEY_HEX" in failed
    assert "STAGING_KNOWLEDGE_SEARCH_KEY_HEX" in failed


def test_enabled_ai_requires_key_and_current_model() -> None:
    environment = _base_environment()
    environment.update(
        {
            "AI_EXTERNAL_CALLS_ENABLED": "true",
            "DEEPSEEK_API_KEY": "",
            "DEEPSEEK_MODEL": "deepseek-chat",
        }
    )

    failed = _failed_names(environment)

    assert "DEEPSEEK_API_KEY" in failed
    assert "DEEPSEEK_MODEL" in failed


def test_direct_provider_signoff_rejects_unreviewed_proxy_base_url() -> None:
    environment = _base_environment()
    environment.update(
        {
            "AI_EXTERNAL_CALLS_ENABLED": "true",
            "DEEPSEEK_API_KEY": "sk-staging-secret-that-is-long-enough",
            "DEEPSEEK_BASE_URL": "https://proxy.example.com/",
        }
    )

    assert "DEEPSEEK_BASE_URL" in _failed_names(environment)


def test_web_origin_must_be_explicitly_allowed() -> None:
    environment = _base_environment()
    environment["AUTH_ALLOWED_ORIGINS"] = "https://different.example.com"

    assert "AUTH_ALLOWED_ORIGINS" in _failed_names(environment)


def test_production_environment_is_rejected_by_staging_preflight() -> None:
    environment = _base_environment()
    environment["APP_ENV"] = "production"

    assert "APP_ENV" in _failed_names(environment)
