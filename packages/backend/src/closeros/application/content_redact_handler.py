"""Outbox handler for deterministic content redaction jobs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.content_encryption_service import (
    ContentEncryptionService,
    ContentEncryptionUnavailableError,
)
from closeros.application.content_sanitization_persistence import DuplicateContentSanitizationError
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.metrics_enqueue_service import MetricsEnqueueService
from closeros.application.privacy_audit import (
    content_sanitization_blocked_event,
    content_sanitization_completed_event,
)
from closeros.application.privacy_sanitizer import sanitize_text
from closeros.domain.audit import AuditActorType
from closeros.domain.content_sanitization import (
    ContentSanitization,
    ContentSanitizationCategoryCount,
    default_policy_version,
)
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    EncryptedContentKind,
)
from closeros.domain.outbox import OutboxErrorCode, OutboxJob
from closeros.domain.privacy_redaction import (
    DETECTOR_VERSION,
    AnalysisEligibility,
    DetectionSummary,
    SanitizationStatus,
)

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_SUPPORTED_RESOURCE_TYPES = frozenset({"message", "message_edit_event"})


class ContentRedactHandlerError(Exception):
    def __init__(self, *, error_code: OutboxErrorCode, permanent: bool) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("content redaction failed")


class ContentRedactHandler:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        content_encryption: ContentEncryptionService,
        metrics_enqueue: MetricsEnqueueService,
        service_actor_id: UUID,
        uuid_factory: _UuidFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._content_encryption = content_encryption
        self._metrics_enqueue = metrics_enqueue
        self._service_actor_id = service_actor_id
        self._uuid_factory = uuid_factory

    async def handle(self, *, job: OutboxJob) -> None:
        if job.tenant_id is None:
            raise ContentRedactHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )
        reference = job.reference
        if reference.resource_type not in _SUPPORTED_RESOURCE_TYPES:
            raise ContentRedactHandlerError(
                error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                permanent=True,
            )
        if reference.secondary_id is None:
            raise ContentRedactHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )

        policy_version = default_policy_version()
        uow = self._uow_factory()
        async with uow:
            existing = await uow.content_sanitizations.get_completed_by_source(
                tenant_id=job.tenant_id,
                source_content_id=reference.secondary_id,
                policy_version=policy_version,
            )
            if existing is not None:
                return

            source_content_id = await self._resolve_and_validate_source(
                uow=uow,
                tenant_id=job.tenant_id,
                resource_type=reference.resource_type,
                resource_id=reference.resource_id,
                expected_content_id=reference.secondary_id,
            )

        audit_context = AuditContext(correlation_id=job.id)
        occurred_at = job.created_at
        decrypted = await self._content_encryption.load_and_decrypt(
            tenant_id=job.tenant_id,
            content_id=source_content_id,
            purpose=ContentAccessPurpose.REDACTION,
            occurred_at=occurred_at,
            audit_context=audit_context,
            actor_type=AuditActorType.SERVICE,
            actor_id=self._service_actor_id,
            audit_event_id=self._uuid_factory(),
        )
        if decrypted.kind is not EncryptedContentKind.RAW_MESSAGE:
            raise ContentRedactHandlerError(
                error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                permanent=True,
            )
        if decrypted.encoding is not ContentEncoding.UTF8:
            await self._persist_blocked(
                job=job,
                resource_type=reference.resource_type,
                resource_id=reference.resource_id,
                source_content_id=source_content_id,
                finding_count=0,
                critical_finding_count=0,
                reason_code="unsupported_encoding",
                audit_context=audit_context,
                occurred_at=occurred_at,
            )
            return

        result = sanitize_text(raw_bytes=decrypted.as_bytes())
        uow = self._uow_factory()
        async with uow:
            try:
                sanitized_content_id: UUID | None = None
                if result.eligibility is AnalysisEligibility.ELIGIBLE:
                    sanitized_content_id = self._uuid_factory()
                    await self._content_encryption.encrypt_and_persist(
                        uow,
                        content_id=sanitized_content_id,
                        tenant_id=job.tenant_id,
                        kind=EncryptedContentKind.SANITIZED_MESSAGE,
                        encoding=ContentEncoding.UTF8,
                        plaintext=result.sanitized_text.encode("utf-8"),
                        created_at=occurred_at,
                    )

                category_counts = _category_counts_from_summary(result.summary)
                sanitization_id = self._uuid_factory()
                record = ContentSanitization(
                    id=sanitization_id,
                    tenant_id=job.tenant_id,
                    source_content_id=source_content_id,
                    sanitized_content_id=sanitized_content_id,
                    source_resource_type=reference.resource_type,
                    source_resource_id=reference.resource_id,
                    policy_version=policy_version,
                    detector_version=DETECTOR_VERSION,
                    status=SanitizationStatus.COMPLETED,
                    analysis_eligibility=result.eligibility,
                    total_finding_count=result.summary.total_count,
                    critical_finding_count=result.summary.critical_count,
                    created_at=occurred_at,
                    completed_at=occurred_at,
                    failure_code=result.failure_code,
                    category_counts=category_counts,
                )
                await uow.content_sanitizations.append_completed(record=record)
                audit_event_id = self._uuid_factory()
                if result.eligibility is AnalysisEligibility.BLOCKED:
                    await append_required_audit_event(
                        uow.audit_events,
                        content_sanitization_blocked_event(
                            tenant_id=job.tenant_id,
                            sanitization_id=sanitization_id,
                            finding_count=result.summary.total_count,
                            critical_finding_count=result.summary.critical_count,
                            eligibility_code=result.eligibility.value,
                            policy_version=policy_version,
                            reason_code=(
                                result.failure_code.value
                                if result.failure_code is not None
                                else "blocked"
                            ),
                            occurred_at=occurred_at,
                            audit_context=audit_context,
                            actor_type=AuditActorType.SERVICE,
                            actor_id=self._service_actor_id,
                            event_id=audit_event_id,
                        ),
                    )
                else:
                    await append_required_audit_event(
                        uow.audit_events,
                        content_sanitization_completed_event(
                            tenant_id=job.tenant_id,
                            sanitization_id=sanitization_id,
                            finding_count=result.summary.total_count,
                            critical_finding_count=result.summary.critical_count,
                            eligibility_code=result.eligibility.value,
                            policy_version=policy_version,
                            detector_version=DETECTOR_VERSION,
                            occurred_at=occurred_at,
                            audit_context=audit_context,
                            actor_type=AuditActorType.SERVICE,
                            actor_id=self._service_actor_id,
                            event_id=audit_event_id,
                        ),
                    )
                await uow.commit()
            except (
                ContentEncryptionUnavailableError,
                DuplicateContentSanitizationError,
            ) as error:
                await uow.rollback()
                if isinstance(error, DuplicateContentSanitizationError):
                    return
                raise ContentRedactHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=False,
                ) from error
            except Exception as error:
                await uow.rollback()
                raise ContentRedactHandlerError(
                    error_code=OutboxErrorCode.HANDLER_FAILED,
                    permanent=False,
                ) from error

        if result.eligibility is AnalysisEligibility.ELIGIBLE:
            tenant = await self._load_tenant_timezone(tenant_id=job.tenant_id)
            if tenant is not None:
                await self._metrics_enqueue.enqueue_tenant_recalculation(
                    tenant_id=job.tenant_id,
                    time_zone=tenant,
                    requested_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self._service_actor_id,
                )

    async def _persist_blocked(
        self,
        *,
        job: OutboxJob,
        resource_type: str,
        resource_id: UUID,
        source_content_id: UUID,
        finding_count: int,
        critical_finding_count: int,
        reason_code: str,
        audit_context: AuditContext,
        occurred_at: datetime,
    ) -> None:
        tenant_id = job.tenant_id
        if tenant_id is None:
            raise ContentRedactHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )
        policy_version = default_policy_version()
        uow = self._uow_factory()
        async with uow:
            sanitization_id = self._uuid_factory()
            record = ContentSanitization(
                id=sanitization_id,
                tenant_id=tenant_id,
                source_content_id=source_content_id,
                sanitized_content_id=None,
                source_resource_type=resource_type,
                source_resource_id=resource_id,
                policy_version=policy_version,
                detector_version=DETECTOR_VERSION,
                status=SanitizationStatus.COMPLETED,
                analysis_eligibility=AnalysisEligibility.BLOCKED,
                total_finding_count=finding_count,
                critical_finding_count=critical_finding_count,
                created_at=occurred_at,
                completed_at=occurred_at,
                failure_code=None,
                category_counts=(),
            )
            try:
                await uow.content_sanitizations.append_completed(record=record)
                await append_required_audit_event(
                    uow.audit_events,
                    content_sanitization_blocked_event(
                        tenant_id=tenant_id,
                        sanitization_id=sanitization_id,
                        finding_count=finding_count,
                        critical_finding_count=critical_finding_count,
                        eligibility_code=AnalysisEligibility.BLOCKED.value,
                        policy_version=policy_version,
                        reason_code=reason_code,
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                        actor_type=AuditActorType.SERVICE,
                        actor_id=self._service_actor_id,
                        event_id=self._uuid_factory(),
                    ),
                )
                await uow.commit()
            except DuplicateContentSanitizationError:
                await uow.rollback()

    async def _resolve_and_validate_source(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        resource_type: str,
        resource_id: UUID,
        expected_content_id: UUID,
    ) -> UUID:
        if resource_type == "message":
            message = await uow.messages.get_for_update(
                tenant_id=tenant_id,
                message_id=resource_id,
            )
            if message is None:
                raise ContentRedactHandlerError(
                    error_code=OutboxErrorCode.MISSING_CANONICAL_PARENT,
                    permanent=True,
                )
            if message.content_id != expected_content_id:
                raise ContentRedactHandlerError(
                    error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                    permanent=True,
                )
            return expected_content_id

        edit_event = await uow.message_edit_events.get_for_update(
            tenant_id=tenant_id,
            event_id=resource_id,
        )
        if edit_event is None:
            raise ContentRedactHandlerError(
                error_code=OutboxErrorCode.MISSING_CANONICAL_PARENT,
                permanent=True,
            )
        if edit_event.content_id != expected_content_id:
            raise ContentRedactHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )
        return expected_content_id

    async def _load_tenant_timezone(self, *, tenant_id: UUID) -> str | None:
        uow = self._uow_factory()
        async with uow:
            tenant = await uow.tenants.get_by_id(tenant_id=tenant_id)
            if tenant is None:
                return None
            return tenant.time_zone


def _category_counts_from_summary(
    summary: DetectionSummary,
) -> tuple[ContentSanitizationCategoryCount, ...]:
    counts = Counter(finding.category.value for finding in summary.findings)
    return tuple(
        ContentSanitizationCategoryCount(category=category, count=count)
        for category, count in sorted(counts.items())
    )
