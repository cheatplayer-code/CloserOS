"""Audit event builders for authentication workflows."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from closeros.application.audit_recording import AuditContext
from closeros.domain.audit import (
    AuditAction,
    AuditActorType,
    AuditEvent,
    AuditScope,
    AuditTargetType,
    MetadataScalar,
    build_audit_event,
)
from closeros.domain.authentication import AuthenticationAssuranceLevel, AuthenticationSessionStage


def _request_metadata(audit_context: AuditContext) -> dict[str, MetadataScalar]:
    metadata: dict[str, MetadataScalar] = {"outcome": "success"}
    if audit_context.http_method is not None:
        metadata["http_method"] = audit_context.http_method
    if audit_context.route_template is not None:
        metadata["route_template"] = audit_context.route_template
    return metadata


def registration_completed_event(
    *,
    user_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    event_id: UUID | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action=AuditAction.USER_REGISTRATION_COMPLETED,
        target_type=AuditTargetType.USER,
        target_id=user_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_request_metadata(audit_context),
    )


def email_verification_requested_event(
    *,
    user_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    event_id: UUID | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action=AuditAction.USER_EMAIL_VERIFICATION_REQUESTED,
        target_type=AuditTargetType.USER,
        target_id=user_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_request_metadata(audit_context),
    )


def email_verification_completed_event(
    *,
    user_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    event_id: UUID | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action=AuditAction.USER_EMAIL_VERIFICATION_COMPLETED,
        target_type=AuditTargetType.USER,
        target_id=user_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_request_metadata(audit_context),
    )


def login_succeeded_event(
    *,
    user_id: UUID,
    session_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    session_stage: AuthenticationSessionStage,
    assurance_level: AuthenticationAssuranceLevel,
    event_id: UUID | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action=AuditAction.AUTH_LOGIN_SUCCEEDED,
        target_type=AuditTargetType.SESSION,
        target_id=session_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={
            **_request_metadata(audit_context),
            "session_stage": session_stage.value,
            "assurance_level": assurance_level.value,
        },
    )


def login_failed_event(
    *,
    occurred_at: datetime,
    audit_context: AuditContext,
    reason_code: str = "invalid_credentials",
    event_id: UUID | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.ANONYMOUS,
        actor_id=None,
        action=AuditAction.AUTH_LOGIN_FAILED,
        target_type=AuditTargetType.AUTHENTICATION,
        target_id=None,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={
            "outcome": "failure",
            "reason_code": reason_code,
        },
    )


def mfa_completed_event(
    *,
    user_id: UUID,
    session_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    mfa_method: str,
    event_id: UUID | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action=AuditAction.AUTH_MFA_COMPLETED,
        target_type=AuditTargetType.SESSION,
        target_id=session_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={
            **_request_metadata(audit_context),
            "mfa_method": mfa_method,
            "assurance_level": AuthenticationAssuranceLevel.MULTI_FACTOR.value,
        },
    )


def mfa_failed_event(
    *,
    user_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    mfa_method: str,
    reason_code: str = "verification_failed",
    event_id: UUID | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action=AuditAction.AUTH_MFA_FAILED,
        target_type=AuditTargetType.AUTHENTICATION,
        target_id=None,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={
            "outcome": "failure",
            "reason_code": reason_code,
            "mfa_method": mfa_method,
        },
    )


def session_revoked_event(
    *,
    user_id: UUID,
    session_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    event_id: UUID | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action=AuditAction.AUTH_SESSION_REVOKED,
        target_type=AuditTargetType.SESSION,
        target_id=session_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_request_metadata(audit_context),
    )


def sessions_revoked_all_event(
    *,
    user_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    affected_count: int,
    event_id: UUID | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action=AuditAction.AUTH_SESSION_REVOKED_ALL,
        target_type=AuditTargetType.USER,
        target_id=user_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={
            **_request_metadata(audit_context),
            "affected_count": affected_count,
        },
    )


def password_reset_requested_event(
    *,
    user_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    event_id: UUID | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action=AuditAction.AUTH_PASSWORD_RESET_REQUESTED,
        target_type=AuditTargetType.USER,
        target_id=user_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_request_metadata(audit_context),
    )


def password_reset_completed_event(
    *,
    user_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    event_id: UUID | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action=AuditAction.AUTH_PASSWORD_RESET_COMPLETED,
        target_type=AuditTargetType.USER,
        target_id=user_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_request_metadata(audit_context),
    )


def password_changed_event(
    *,
    user_id: UUID,
    session_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    event_id: UUID | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action=AuditAction.AUTH_PASSWORD_CHANGED,
        target_type=AuditTargetType.USER,
        target_id=user_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={
            **_request_metadata(audit_context),
            "session_stage": AuthenticationSessionStage.AUTHENTICATED.value,
        },
    )
