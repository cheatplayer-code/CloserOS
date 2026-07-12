"""Synthetic helpers for authentication workflow tests."""

from __future__ import annotations

from base64 import urlsafe_b64encode
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from closeros.application.audit_recording import AuditContext
from closeros.domain.authentication import MfaMethod
from closeros.security.authentication_tokens import RawAuthenticationToken

NOW = datetime(2026, 7, 12, 8, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)

USER_ID = UUID("00000000-0000-0000-0000-000000000010")
CREDENTIAL_ID = UUID("00000000-0000-0000-0000-000000000020")
VERIFICATION_TOKEN_ID = UUID("00000000-0000-0000-0000-000000000030")
RESET_TOKEN_ID = UUID("00000000-0000-0000-0000-000000000040")
SESSION_ID = UUID("00000000-0000-0000-0000-000000000100")
NEW_SESSION_ID = UUID("00000000-0000-0000-0000-000000000101")
OTHER_SESSION_ID = UUID("00000000-0000-0000-0000-000000000102")
CORRELATION_ID = UUID("00000000-0000-0000-0000-000000000999")
TEST_AUDIT_CONTEXT = AuditContext(correlation_id=CORRELATION_ID)

REGISTER_EMAIL = "workflow.test@example.test"
REGISTER_PASSWORD = "Synthetic-Password-1"
OTHER_PASSWORD = "Synthetic-Password-2"

TOKEN_ENTROPY_A = bytes(range(32))
TOKEN_ENTROPY_B = bytes(reversed(range(32)))
TOKEN_ENTROPY_C = bytes((index * 7) % 256 for index in range(32))


def raw_token_from_entropy(entropy: bytes) -> RawAuthenticationToken:
    encoded = urlsafe_b64encode(entropy).rstrip(b"=").decode("ascii")
    return RawAuthenticationToken(encoded)


def deterministic_token_factory(
    entropy: bytes,
) -> Callable[[], RawAuthenticationToken]:
    token = raw_token_from_entropy(entropy)

    def factory() -> RawAuthenticationToken:
        return token

    return factory


class AcceptingMfaVerifier:
    async def verify_mfa(
        self,
        *,
        user_id: UUID,
        method: MfaMethod,
        response: object,
    ) -> bool:
        return True


class RejectingMfaVerifier:
    async def verify_mfa(
        self,
        *,
        user_id: UUID,
        method: MfaMethod,
        response: object,
    ) -> bool:
        return False
