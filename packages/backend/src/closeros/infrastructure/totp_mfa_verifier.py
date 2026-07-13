"""Production TOTP MFA verifier with encrypted enrollment secrets."""

from __future__ import annotations

import hashlib
import hmac
import struct
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.domain.audit import AuditActorType
from closeros.domain.authentication import MfaMethod
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    EncryptedContentKind,
)

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]

_TOTP_TIMESTEP_SECONDS = 30
_TOTP_DIGITS = 6
_TOTP_WINDOW_STEPS = 1
_PLATFORM_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000f0")


class MfaVerificationRejectedError(Exception):
    """Raised when MFA verification fails without leaking secrets."""


def _compute_totp(*, secret: bytes, timestep: int) -> str:
    counter = struct.pack(">Q", timestep)
    digest = hmac.new(secret, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = truncated % (10**_TOTP_DIGITS)
    return str(code).zfill(_TOTP_DIGITS)


def _parse_totp_response(response: object) -> str:
    if isinstance(response, dict):
        raw_code = response.get("code")
        if isinstance(raw_code, str) and raw_code.strip():
            return raw_code.strip()
    raise MfaVerificationRejectedError("mfa response is invalid")


@dataclass(frozen=True, slots=True)
class DatabaseTotpMfaVerifier:
    """Verifies TOTP codes against persisted encrypted enrollment secrets."""

    uow_factory: _UnitOfWorkFactory
    content_encryption: ContentEncryptionService
    service_actor_id: UUID
    uuid_factory: _UuidFactory

    def __repr__(self) -> str:
        return "DatabaseTotpMfaVerifier()"

    async def verify_mfa(
        self,
        *,
        user_id: UUID,
        method: MfaMethod,
        response: object,
    ) -> bool:
        if method is not MfaMethod.TOTP:
            return False
        try:
            submitted_code = _parse_totp_response(response)
        except MfaVerificationRejectedError:
            return False
        if not submitted_code.isdigit() or len(submitted_code) != _TOTP_DIGITS:
            return False

        uow = self.uow_factory()
        async with uow:
            enrollment = await uow.user_mfa_totp_enrollments.get_by_user_id(user_id=user_id)
            if enrollment is None:
                return False

            occurred_at = datetime.now(tz=UTC)
            decrypted = await self.content_encryption.load_and_decrypt(
                tenant_id=enrollment.secret_tenant_id,
                content_id=enrollment.encrypted_secret_content_id,
                purpose=ContentAccessPurpose.MFA_TOTP_VERIFY,
                occurred_at=occurred_at,
                audit_context=AuditContext(correlation_id=self.uuid_factory()),
                actor_type=AuditActorType.SERVICE,
                actor_id=self.service_actor_id,
                audit_event_id=self.uuid_factory(),
            )
            secret = decrypted.as_bytes()
            current_step = int(occurred_at.timestamp()) // _TOTP_TIMESTEP_SECONDS

            matched_step: int | None = None
            for step_offset in range(-_TOTP_WINDOW_STEPS, _TOTP_WINDOW_STEPS + 1):
                candidate_step = current_step + step_offset
                if _compute_totp(secret=secret, timestep=candidate_step) == submitted_code:
                    matched_step = candidate_step
                    break
            if matched_step is None:
                return False

            if (
                enrollment.last_accepted_timestep is not None
                and matched_step <= enrollment.last_accepted_timestep
            ):
                return False

            await uow.user_mfa_totp_enrollments.update_last_accepted_timestep(
                user_id=user_id,
                last_accepted_timestep=matched_step,
                updated_at=occurred_at,
            )
            await uow.commit()
        return True


async def enroll_totp_secret_for_tests(
    *,
    uow_factory: _UnitOfWorkFactory,
    content_encryption: ContentEncryptionService,
    user_id: UUID,
    secret: bytes,
    occurred_at: datetime,
    uuid_factory: _UuidFactory,
) -> None:
    """Test helper to persist encrypted TOTP enrollment without exposing secrets in fixtures."""
    if not secret:
        raise ValueError("secret must not be empty")
    content_id = uuid_factory()
    uow = uow_factory()
    async with uow:
        existing_user = await uow.users.get_by_id(user_id)
        if existing_user is None:
            from closeros.domain.identity import UserStatus
            from closeros.domain.user import User

            await uow.users.add(User(id=user_id, status=UserStatus.ACTIVE))
        await content_encryption.encrypt_and_persist(
            uow,
            content_id=content_id,
            tenant_id=_PLATFORM_TENANT_ID,
            kind=EncryptedContentKind.MFA_TOTP_SECRET,
            encoding=ContentEncoding.UTF8,
            plaintext=secret,
            created_at=occurred_at,
        )
        await uow.user_mfa_totp_enrollments.upsert(
            user_id=user_id,
            secret_tenant_id=_PLATFORM_TENANT_ID,
            encrypted_secret_content_id=content_id,
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        await uow.commit()


__all__ = [
    "DatabaseTotpMfaVerifier",
    "MfaVerificationRejectedError",
    "enroll_totp_secret_for_tests",
]
