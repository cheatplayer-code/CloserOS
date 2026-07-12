"""Tests for environment-backed WhatsApp credential resolver."""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

import pytest
from closeros.domain.provider_credentials import SecretBytes
from closeros.infrastructure.env_whatsapp_credential_resolver import EnvWhatsAppCredentialResolver

from tests.vw_support import (
    VW_ACCESS_TOKEN,
    VW_ACCESS_TOKEN_REF,
    VW_APP_SECRET,
    VW_APP_SECRET_REF,
    VW_VERIFY_TOKEN_REF,
    build_runtime_secret,
    vw_credential_environ,
)


def test_env_resolver_returns_secret_for_reference_key() -> None:
    resolver = EnvWhatsAppCredentialResolver(environ=vw_credential_environ())

    async def exercise() -> SecretBytes | None:
        return await resolver.resolve_access_token(
            tenant_id=uuid4(),
            whatsapp_connection_id=uuid4(),
            reference_key=VW_ACCESS_TOKEN_REF,
        )

    secret = asyncio.run(exercise())
    assert secret is not None
    assert secret.value == VW_ACCESS_TOKEN


def test_env_resolver_returns_none_for_missing_reference() -> None:
    resolver = EnvWhatsAppCredentialResolver(environ={})

    async def exercise() -> SecretBytes | None:
        return await resolver.resolve_app_secret(
            tenant_id=uuid4(),
            whatsapp_connection_id=uuid4(),
            reference_key=VW_APP_SECRET_REF,
        )

    assert asyncio.run(exercise()) is None


def test_env_resolver_does_not_log_secret_values(caplog: pytest.LogCaptureFixture) -> None:
    token = build_runtime_secret("caplog", "-", "token")
    environ = {VW_VERIFY_TOKEN_REF: token.decode("utf-8")}
    resolver = EnvWhatsAppCredentialResolver(environ=environ)

    async def exercise() -> None:
        await resolver.resolve_verify_token(
            tenant_id=uuid4(),
            whatsapp_connection_id=uuid4(),
            reference_key=VW_VERIFY_TOKEN_REF,
        )

    with caplog.at_level(logging.DEBUG):
        asyncio.run(exercise())

    joined = " ".join(record.getMessage() for record in caplog.records)
    assert token.decode("utf-8") not in joined
    assert VW_APP_SECRET.decode("utf-8") not in joined


def test_secret_bytes_repr_hides_value() -> None:
    secret = SecretBytes(value=VW_APP_SECRET)
    assert VW_APP_SECRET.decode("utf-8") not in repr(secret)
