"""Application services for encrypted-content encryption, decryption, and rewrap."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.content_audit import (
    content_encrypted_accessed_event,
    content_key_rewrapped_event,
)
from closeros.application.encrypted_content_persistence import (
    EncryptedContentRecordNotFoundError,
)
from closeros.application.encryption_ports import (
    DataKeyCryptography,
    RetentionExpiryCalculator,
)
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.domain.audit import AuditActorType
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    ContentUnavailableError,
    DecryptedContent,
    EncryptedContent,
    EncryptedContentKind,
    validate_plaintext_for_kind,
)
from closeros.domain.identity import TenantStatus
from closeros.domain.tenant import Tenant


class ContentEncryptionError(Exception):
    """Base class for safe encrypted-content service failures."""


class ContentEncryptionUnavailableError(ContentEncryptionError):
    """Raised when encrypted content cannot be stored, loaded, or rewrapped."""


class ContentAccessDeniedError(ContentEncryptionError):
    """Raised when a content-access purpose is not permitted for the kind."""


class ContentTenantUnavailableError(ContentEncryptionError):
    """Raised when the tenant cannot be resolved for encrypted-content writes."""


_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]

_PURPOSES_BY_KIND: dict[EncryptedContentKind, frozenset[ContentAccessPurpose]] = {
    EncryptedContentKind.RAW_MESSAGE: frozenset(
        {
            ContentAccessPurpose.REDACTION,
            ContentAccessPurpose.AUDIT_REVIEW,
            ContentAccessPurpose.RETENTION_DELETION,
        }
    ),
    EncryptedContentKind.SANITIZED_MESSAGE: frozenset(
        {
            ContentAccessPurpose.AI_ANALYSIS,
            ContentAccessPurpose.CONVERSATION_REVIEW,
            ContentAccessPurpose.AUDIT_REVIEW,
            ContentAccessPurpose.RETENTION_DELETION,
        }
    ),
    EncryptedContentKind.PROVIDER_PAYLOAD: frozenset(
        {
            ContentAccessPurpose.WEBHOOK_NORMALIZATION,
            ContentAccessPurpose.AUDIT_REVIEW,
            ContentAccessPurpose.RETENTION_DELETION,
        }
    ),
    EncryptedContentKind.CSV_IMPORT: frozenset(
        {
            ContentAccessPurpose.CSV_IMPORT_PROCESSING,
            ContentAccessPurpose.AUDIT_REVIEW,
            ContentAccessPurpose.RETENTION_DELETION,
        }
    ),
    EncryptedContentKind.KNOWLEDGE_DOCUMENT: frozenset(
        {
            ContentAccessPurpose.KNOWLEDGE_RETRIEVAL,
            ContentAccessPurpose.AUDIT_REVIEW,
            ContentAccessPurpose.RETENTION_DELETION,
        }
    ),
    EncryptedContentKind.KNOWLEDGE_CHUNK: frozenset(
        {
            ContentAccessPurpose.KNOWLEDGE_RETRIEVAL,
            ContentAccessPurpose.AI_ANALYSIS,
            ContentAccessPurpose.AUDIT_REVIEW,
            ContentAccessPurpose.RETENTION_DELETION,
        }
    ),
}


def _validate_uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")
    return value


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _raise_unavailable() -> NoReturn:
    raise ContentEncryptionUnavailableError("encrypted content is unavailable")


def _assert_access_purpose(
    *,
    kind: EncryptedContentKind,
    purpose: ContentAccessPurpose,
) -> None:
    allowed_purposes = _PURPOSES_BY_KIND.get(kind)
    if allowed_purposes is None or purpose not in allowed_purposes:
        raise ContentAccessDeniedError("content access purpose is not permitted")


async def _load_active_tenant(
    uow: IntegratedUnitOfWork,
    *,
    tenant_id: UUID,
) -> Tenant:
    tenant = await uow.tenants.get_by_id(tenant_id)
    if tenant is None or tenant.status is not TenantStatus.ACTIVE:
        raise ContentTenantUnavailableError("tenant is unavailable for encrypted content")
    return tenant


@dataclass(frozen=True, slots=True)
class ContentEncryptionService:
    """Encrypts, decrypts, and rewraps tenant-bound encrypted content."""

    data_key_cryptography: DataKeyCryptography
    retention_expiry_calculator: RetentionExpiryCalculator
    uow_factory: _UnitOfWorkFactory

    def __repr__(self) -> str:
        return "ContentEncryptionService()"

    async def encrypt_and_persist(
        self,
        uow: IntegratedUnitOfWork,
        *,
        content_id: UUID,
        tenant_id: UUID,
        kind: EncryptedContentKind,
        encoding: ContentEncoding,
        plaintext: bytes,
        created_at: datetime,
    ) -> EncryptedContent:
        validated_content_id = _validate_uuid(content_id, "content_id")
        validated_tenant_id = _validate_uuid(tenant_id, "tenant_id")
        validated_created_at = _validate_timezone_aware_datetime(created_at, "created_at")

        if not isinstance(kind, EncryptedContentKind):
            raise TypeError("kind must be an EncryptedContentKind")
        if not isinstance(encoding, ContentEncoding):
            raise TypeError("encoding must be a ContentEncoding")

        tenant = await _load_active_tenant(uow, tenant_id=validated_tenant_id)
        validated_plaintext = validate_plaintext_for_kind(kind=kind, plaintext=plaintext)
        expires_at = self.retention_expiry_calculator.calculate_expires_at(
            kind=kind,
            created_at=validated_created_at,
            policy=tenant.retention_policy,
        )

        try:
            encrypted = self.data_key_cryptography.encrypt_plaintext(
                content_id=validated_content_id,
                tenant_id=validated_tenant_id,
                kind=kind,
                encoding=encoding,
                plaintext=validated_plaintext,
                created_at=validated_created_at,
                expires_at=expires_at,
            )
            await uow.encrypted_contents.add(encrypted)
        except ContentEncryptionError:
            raise
        except Exception as error:
            raise ContentEncryptionUnavailableError(
                "encrypted content persistence failed"
            ) from error

        return encrypted

    async def load_and_decrypt(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        purpose: ContentAccessPurpose,
        occurred_at: datetime,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
        audit_event_id: UUID,
    ) -> DecryptedContent:
        validated_tenant_id = _validate_uuid(tenant_id, "tenant_id")
        validated_content_id = _validate_uuid(content_id, "content_id")
        validated_occurred_at = _validate_timezone_aware_datetime(occurred_at, "occurred_at")
        validated_audit_event_id = _validate_uuid(audit_event_id, "audit_event_id")

        if not isinstance(purpose, ContentAccessPurpose):
            raise TypeError("purpose must be a ContentAccessPurpose")

        uow = self.uow_factory()
        async with uow:
            encrypted = await uow.encrypted_contents.get_by_id(
                tenant_id=validated_tenant_id,
                content_id=validated_content_id,
            )
            if encrypted is None:
                _raise_unavailable()

            _assert_access_purpose(kind=encrypted.kind, purpose=purpose)

            try:
                decrypted = self.data_key_cryptography.decrypt_content(encrypted=encrypted)
            except ContentUnavailableError as error:
                raise ContentEncryptionUnavailableError(
                    "encrypted content is unavailable"
                ) from error

            await append_required_audit_event(
                uow.audit_events,
                content_encrypted_accessed_event(
                    tenant_id=validated_tenant_id,
                    content_id=validated_content_id,
                    kind=encrypted.kind,
                    purpose=purpose,
                    key_version=encrypted.key_version,
                    occurred_at=validated_occurred_at,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=validated_audit_event_id,
                ),
            )
            await uow.commit()

        return decrypted

    async def rewrap_content_key(
        self,
        uow: IntegratedUnitOfWork,
        *,
        tenant_id: UUID,
        content_id: UUID,
        occurred_at: datetime,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
        audit_event_id: UUID,
    ) -> EncryptedContent:
        validated_tenant_id = _validate_uuid(tenant_id, "tenant_id")
        validated_content_id = _validate_uuid(content_id, "content_id")
        validated_occurred_at = _validate_timezone_aware_datetime(occurred_at, "occurred_at")
        validated_audit_event_id = _validate_uuid(audit_event_id, "audit_event_id")

        encrypted = await uow.encrypted_contents.get_for_update(
            tenant_id=validated_tenant_id,
            content_id=validated_content_id,
        )
        if encrypted is None:
            _raise_unavailable()

        previous_key_version = encrypted.key_version

        try:
            wrapped = self.data_key_cryptography.rewrap_data_key(encrypted=encrypted)
            await uow.encrypted_contents.replace_wrapped_key(
                tenant_id=validated_tenant_id,
                content_id=validated_content_id,
                wrapped_data_key=wrapped,
            )
        except (
            ContentUnavailableError,
            EncryptedContentRecordNotFoundError,
        ) as error:
            raise ContentEncryptionUnavailableError("encrypted content rewrap failed") from error
        except Exception as error:
            raise ContentEncryptionUnavailableError("encrypted content rewrap failed") from error

        updated = replace(
            encrypted,
            wrapped_data_key=wrapped.wrapped_data_key,
            key_wrap_nonce=wrapped.key_wrap_nonce,
            key_version=wrapped.key_version,
        )

        await append_required_audit_event(
            uow.audit_events,
            content_key_rewrapped_event(
                tenant_id=validated_tenant_id,
                content_id=validated_content_id,
                kind=encrypted.kind,
                previous_key_version=previous_key_version,
                key_version=updated.key_version,
                occurred_at=validated_occurred_at,
                audit_context=audit_context,
                actor_type=actor_type,
                actor_id=actor_id,
                event_id=validated_audit_event_id,
            ),
        )

        return updated
