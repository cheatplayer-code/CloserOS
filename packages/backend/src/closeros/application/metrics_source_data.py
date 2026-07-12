"""Tenant-scoped canonical rows used by the deterministic metrics engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.domain.canonical_enums import (
    CrmOutcomeType,
    DeliveryStatus,
    MessageDirection,
    ParticipantSenderType,
    SalesCaseStatus,
)


@dataclass(frozen=True, slots=True)
class MetricsMessageRow:
    id: UUID
    tenant_id: UUID
    conversation_thread_id: UUID
    sender_type: ParticipantSenderType
    direction: MessageDirection
    received_at: datetime


@dataclass(frozen=True, slots=True)
class MetricsThreadRow:
    id: UUID
    tenant_id: UUID
    sales_case_id: UUID | None


@dataclass(frozen=True, slots=True)
class MetricsDeliveryEventRow:
    conversation_thread_id: UUID
    message_id: UUID
    status: DeliveryStatus
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class MetricsSalesCaseRow:
    id: UUID
    tenant_id: UUID
    status: SalesCaseStatus
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MetricsCrmOutcomeRow:
    sales_case_id: UUID
    outcome_type: CrmOutcomeType
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class MetricsAssignmentRow:
    id: UUID
    tenant_id: UUID
    manager_user_id: UUID
    conversation_thread_id: UUID | None
    sales_case_id: UUID | None
    assigned_at: datetime


@dataclass(frozen=True, slots=True)
class MetricsSourceData:
    messages: tuple[MetricsMessageRow, ...]
    threads: tuple[MetricsThreadRow, ...]
    delivery_events: tuple[MetricsDeliveryEventRow, ...]
    sales_cases: tuple[MetricsSalesCaseRow, ...]
    crm_outcomes: tuple[MetricsCrmOutcomeRow, ...]
    assignments: tuple[MetricsAssignmentRow, ...]
    watermark: datetime
