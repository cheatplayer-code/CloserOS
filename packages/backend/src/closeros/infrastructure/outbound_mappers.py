"""Mappers between outbound/media domain, records, and ORM rows."""

from __future__ import annotations

from closeros.application.outbound_persistence import (
    OutboundDeliveryAttemptRecord,
    OutboundMessageRecord,
)
from closeros.application.provider_media_persistence import ProviderMediaReferenceRecord
from closeros.application.provider_template_persistence import ProviderMessageTemplateRecord
from closeros.domain.outbound_message import (
    OutboundMessage,
    OutboundMessageKind,
    OutboundMessageStatus,
)
from closeros.domain.provider_media_reference import MediaQuarantineStatus, ProviderMediaReference
from closeros.domain.provider_template import (
    ProviderMessageTemplate,
    ProviderTemplateApprovalStatus,
)
from closeros.infrastructure.outbound_orm import (
    OutboundDeliveryAttemptRow,
    OutboundMessageRow,
    ProviderMediaReferenceRow,
)
from closeros.infrastructure.whatsapp_orm import ProviderMessageTemplateRow


def outbound_record_to_domain(record: OutboundMessageRecord) -> OutboundMessage:
    return OutboundMessage(
        id=record.id,
        tenant_id=record.tenant_id,
        conversation_thread_id=record.conversation_thread_id,
        channel_connection_id=record.channel_connection_id,
        kind=record.kind,
        status=record.status,
        encrypted_content_id=record.encrypted_content_id,
        provider_template_id=record.provider_template_id,
        created_by_user_id=record.created_by_user_id,
        approved_by_user_id=record.approved_by_user_id,
        provider_message_id=record.provider_message_id,
        failure_code=record.failure_code,
        created_at=record.created_at,
        approved_at=record.approved_at,
        queued_at=record.queued_at,
        sent_at=record.sent_at,
        completed_at=record.completed_at,
        updated_at=record.updated_at,
        version=record.version,
    )


def outbound_domain_to_record(message: OutboundMessage) -> OutboundMessageRecord:
    return OutboundMessageRecord(
        id=message.id,
        tenant_id=message.tenant_id,
        conversation_thread_id=message.conversation_thread_id,
        channel_connection_id=message.channel_connection_id,
        kind=message.kind,
        status=message.status,
        encrypted_content_id=message.encrypted_content_id,
        provider_template_id=message.provider_template_id,
        created_by_user_id=message.created_by_user_id,
        approved_by_user_id=message.approved_by_user_id,
        provider_message_id=message.provider_message_id,
        failure_code=message.failure_code,
        created_at=message.created_at,
        approved_at=message.approved_at,
        queued_at=message.queued_at,
        sent_at=message.sent_at,
        completed_at=message.completed_at,
        updated_at=message.updated_at,
        version=message.version,
    )


def outbound_record_to_row(record: OutboundMessageRecord) -> OutboundMessageRow:
    return OutboundMessageRow(
        id=record.id,
        tenant_id=record.tenant_id,
        conversation_thread_id=record.conversation_thread_id,
        channel_connection_id=record.channel_connection_id,
        kind=record.kind.value,
        status=record.status.value,
        encrypted_content_id=record.encrypted_content_id,
        provider_template_id=record.provider_template_id,
        created_by_user_id=record.created_by_user_id,
        approved_by_user_id=record.approved_by_user_id,
        provider_message_id=record.provider_message_id,
        failure_code=record.failure_code,
        created_at=record.created_at,
        approved_at=record.approved_at,
        queued_at=record.queued_at,
        sent_at=record.sent_at,
        completed_at=record.completed_at,
        updated_at=record.updated_at,
        version=record.version,
    )


def outbound_row_to_record(row: OutboundMessageRow) -> OutboundMessageRecord:
    return OutboundMessageRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_thread_id=row.conversation_thread_id,
        channel_connection_id=row.channel_connection_id,
        kind=OutboundMessageKind(row.kind),
        status=OutboundMessageStatus(row.status),
        encrypted_content_id=row.encrypted_content_id,
        provider_template_id=row.provider_template_id,
        created_by_user_id=row.created_by_user_id,
        approved_by_user_id=row.approved_by_user_id,
        provider_message_id=row.provider_message_id,
        failure_code=row.failure_code,
        created_at=row.created_at,
        approved_at=row.approved_at,
        queued_at=row.queued_at,
        sent_at=row.sent_at,
        completed_at=row.completed_at,
        updated_at=row.updated_at,
        version=row.version,
    )


def delivery_attempt_record_to_row(
    record: OutboundDeliveryAttemptRecord,
) -> OutboundDeliveryAttemptRow:
    return OutboundDeliveryAttemptRow(
        id=record.id,
        tenant_id=record.tenant_id,
        outbound_message_id=record.outbound_message_id,
        attempt_number=record.attempt_number,
        started_at=record.started_at,
        finished_at=record.finished_at,
        outcome=record.outcome,
        error_code=record.error_code,
    )


def delivery_attempt_row_to_record(
    row: OutboundDeliveryAttemptRow,
) -> OutboundDeliveryAttemptRecord:
    return OutboundDeliveryAttemptRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        outbound_message_id=row.outbound_message_id,
        attempt_number=row.attempt_number,
        started_at=row.started_at,
        finished_at=row.finished_at,
        outcome=row.outcome,
        error_code=row.error_code,
    )


def media_record_to_domain(record: ProviderMediaReferenceRecord) -> ProviderMediaReference:
    return ProviderMediaReference(
        id=record.id,
        tenant_id=record.tenant_id,
        channel_connection_id=record.channel_connection_id,
        conversation_thread_id=record.conversation_thread_id,
        inbound_message_id=record.inbound_message_id,
        provider_media_id=record.provider_media_id,
        media_type=record.media_type,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        quarantine_status=record.quarantine_status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def media_domain_to_record(reference: ProviderMediaReference) -> ProviderMediaReferenceRecord:
    return ProviderMediaReferenceRecord(
        id=reference.id,
        tenant_id=reference.tenant_id,
        channel_connection_id=reference.channel_connection_id,
        conversation_thread_id=reference.conversation_thread_id,
        inbound_message_id=reference.inbound_message_id,
        provider_media_id=reference.provider_media_id,
        media_type=reference.media_type,
        mime_type=reference.mime_type,
        size_bytes=reference.size_bytes,
        encrypted_content_id=None,
        quarantine_status=reference.quarantine_status,
        created_at=reference.created_at,
        updated_at=reference.updated_at,
    )


def media_record_to_row(record: ProviderMediaReferenceRecord) -> ProviderMediaReferenceRow:
    return ProviderMediaReferenceRow(
        id=record.id,
        tenant_id=record.tenant_id,
        channel_connection_id=record.channel_connection_id,
        conversation_thread_id=record.conversation_thread_id,
        inbound_message_id=record.inbound_message_id,
        provider_media_id=record.provider_media_id,
        media_type=record.media_type,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        encrypted_content_id=record.encrypted_content_id,
        quarantine_status=record.quarantine_status.value,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def media_row_to_record(row: ProviderMediaReferenceRow) -> ProviderMediaReferenceRecord:
    return ProviderMediaReferenceRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        channel_connection_id=row.channel_connection_id,
        conversation_thread_id=row.conversation_thread_id,
        inbound_message_id=row.inbound_message_id,
        provider_media_id=row.provider_media_id,
        media_type=row.media_type,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        encrypted_content_id=row.encrypted_content_id,
        quarantine_status=MediaQuarantineStatus(row.quarantine_status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def template_record_to_domain(record: ProviderMessageTemplateRecord) -> ProviderMessageTemplate:
    return ProviderMessageTemplate(
        id=record.id,
        tenant_id=record.tenant_id,
        whatsapp_connection_id=record.whatsapp_connection_id,
        provider_template_id=record.provider_template_id,
        name=record.name,
        language_code=record.language_code,
        category=record.category,
        approval_status=record.approval_status,
        component_shape=record.component_shape,
        parameter_count=record.parameter_count,
        last_synced_at=record.last_synced_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        version=record.version,
    )


def template_domain_to_record(template: ProviderMessageTemplate) -> ProviderMessageTemplateRecord:
    return ProviderMessageTemplateRecord(
        id=template.id,
        tenant_id=template.tenant_id,
        whatsapp_connection_id=template.whatsapp_connection_id,
        provider_template_id=template.provider_template_id,
        name=template.name,
        language_code=template.language_code,
        category=template.category,
        approval_status=template.approval_status,
        component_shape=template.component_shape,
        parameter_count=template.parameter_count,
        last_synced_at=template.last_synced_at,
        created_at=template.created_at,
        updated_at=template.updated_at,
        version=template.version,
    )


def template_record_to_row(record: ProviderMessageTemplateRecord) -> ProviderMessageTemplateRow:
    return ProviderMessageTemplateRow(
        id=record.id,
        tenant_id=record.tenant_id,
        whatsapp_connection_id=record.whatsapp_connection_id,
        provider_template_id=record.provider_template_id,
        name=record.name,
        language_code=record.language_code,
        category=record.category,
        approval_status=record.approval_status.value,
        component_shape=list(record.component_shape),
        parameter_count=record.parameter_count,
        last_synced_at=record.last_synced_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        version=record.version,
    )


def template_row_to_record(row: ProviderMessageTemplateRow) -> ProviderMessageTemplateRecord:
    return ProviderMessageTemplateRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        whatsapp_connection_id=row.whatsapp_connection_id,
        provider_template_id=row.provider_template_id,
        name=row.name,
        language_code=row.language_code,
        category=row.category,
        approval_status=ProviderTemplateApprovalStatus(row.approval_status),
        component_shape=tuple(row.component_shape),
        parameter_count=row.parameter_count,
        last_synced_at=row.last_synced_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )
