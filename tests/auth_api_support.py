"""Helpers for authentication API tests."""

from __future__ import annotations

from base64 import urlsafe_b64encode
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

from closeros_api.settings import ApiSettings

NOW = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
TEST_CSRF_SECRET = b"test_csrf_secret_value_32_bytes_xx"
TEST_RATE_SECRET = b"test_rate_secret_value_32_bytes_xx"
TEST_ORIGIN = "http://127.0.0.1:3000"
TEST_EMAIL = "api.test@example.test"
TEST_PASSWORD = "Synthetic-Password-1"
OTHER_PASSWORD = "Synthetic-Password-2"

USER_ID = UUID("00000000-0000-0000-0000-000000000010")
CREDENTIAL_ID = UUID("00000000-0000-0000-0000-000000000020")
VERIFICATION_TOKEN_ID = UUID("00000000-0000-0000-0000-000000000030")
SESSION_ID = UUID("00000000-0000-0000-0000-000000000100")
NEW_SESSION_ID = UUID("00000000-0000-0000-0000-000000000101")
RESET_TOKEN_ID = UUID("00000000-0000-0000-0000-000000000040")

TOKEN_ENTROPY_A = bytes(range(32))
TOKEN_ENTROPY_B = bytes(reversed(range(32)))
TOKEN_ENTROPY_C = bytes((index * 11) % 256 for index in range(32))


def development_api_settings(*, database_url: str) -> ApiSettings:
    return ApiSettings(
        app_env="development",
        database_url=database_url,
        auth_allowed_origins=(TEST_ORIGIN, "http://localhost:3000"),
        auth_csrf_secret=TEST_CSRF_SECRET,
        auth_rate_limit_secret=TEST_RATE_SECRET,
        session_touch_interval=timedelta(minutes=5),
        trust_forwarded_client_ip=False,
        webhook_max_body_bytes=1_048_576,
        csv_max_body_bytes=10_485_760,
        ingestion_service_id=UUID("00000000-0000-0000-0000-00000000e001"),
    )


def production_api_settings(*, database_url: str) -> ApiSettings:
    return ApiSettings(
        app_env="production",
        database_url=database_url,
        auth_allowed_origins=("https://app.example.test",),
        auth_csrf_secret=TEST_CSRF_SECRET,
        auth_rate_limit_secret=TEST_RATE_SECRET,
        session_touch_interval=timedelta(minutes=5),
        trust_forwarded_client_ip=False,
        webhook_max_body_bytes=1_048_576,
        csv_max_body_bytes=10_485_760,
        ingestion_service_id=UUID("00000000-0000-0000-0000-00000000e001"),
    )


def deterministic_token_string(entropy: bytes) -> str:
    return urlsafe_b64encode(entropy).rstrip(b"=").decode("ascii")


class FixedClock:
    def __init__(self, moment: datetime = NOW) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class SequenceUuidFactory:
    def __init__(self, values: Iterator[UUID] | list[UUID]) -> None:
        self._values = iter(values)

    def __call__(self) -> UUID:
        return next(self._values)
