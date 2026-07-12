"""Deterministic tenant and manager metrics calculation engine."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from closeros.application.metrics_source_data import (
    MetricsAssignmentRow,
    MetricsMessageRow,
    MetricsSourceData,
)
from closeros.domain.canonical_enums import (
    CrmOutcomeType,
    DeliveryStatus,
    MessageDirection,
    ParticipantSenderType,
    SalesCaseStatus,
)
from closeros.domain.metrics import (
    METRIC_FORMULA_VERSION,
    MetricKey,
    MetricScope,
    MetricSnapshot,
    MetricSnapshotStatus,
    MetricValue,
    MetricWindow,
    deterministic_median_seconds,
    deterministic_p90_seconds,
    floor_basis_points,
)


class MetricsEngine:
    def calculate_snapshot(
        self,
        *,
        snapshot_id: UUID,
        tenant_id: UUID,
        scope: MetricScope,
        manager_user_id: UUID | None,
        window: MetricWindow,
        source_data: MetricsSourceData,
        computed_at: datetime,
    ) -> MetricSnapshot:
        thread_ids = self._threads_for_scope(
            source_data=source_data,
            scope=scope,
            manager_user_id=manager_user_id,
            window_end=window.end,
        )
        messages = tuple(
            message
            for message in source_data.messages
            if message.conversation_thread_id in thread_ids
        )
        values = self._calculate_values(
            messages=messages,
            thread_ids=thread_ids,
            source_data=source_data,
        )
        return MetricSnapshot(
            id=snapshot_id,
            tenant_id=tenant_id,
            scope=scope,
            manager_user_id=manager_user_id,
            window=window,
            formula_version=METRIC_FORMULA_VERSION,
            source_watermark=source_data.watermark,
            computed_at=computed_at,
            status=MetricSnapshotStatus.COMPLETED,
            values=values,
        )

    def _threads_for_scope(
        self,
        *,
        source_data: MetricsSourceData,
        scope: MetricScope,
        manager_user_id: UUID | None,
        window_end: datetime,
    ) -> set[UUID]:
        all_thread_ids = {thread.id for thread in source_data.threads}
        if scope is MetricScope.TENANT:
            return all_thread_ids
        if manager_user_id is None:
            return set()
        attributed_manager_by_thread = self._attribute_threads_to_managers(
            source_data=source_data,
            thread_ids=all_thread_ids,
            window_end=window_end,
        )
        return {
            thread_id
            for thread_id, attributed_manager in attributed_manager_by_thread.items()
            if attributed_manager == manager_user_id
        }

    def _attribute_threads_to_managers(
        self,
        *,
        source_data: MetricsSourceData,
        thread_ids: set[UUID],
        window_end: datetime,
    ) -> dict[UUID, UUID]:
        threads_by_id = {thread.id: thread for thread in source_data.threads}
        winning_assignment_by_thread: dict[UUID, MetricsAssignmentRow] = {}
        winning_assignment_by_sales_case: dict[UUID, MetricsAssignmentRow] = {}

        for assignment in source_data.assignments:
            if assignment.assigned_at > window_end:
                continue
            if assignment.conversation_thread_id is not None:
                current = winning_assignment_by_thread.get(assignment.conversation_thread_id)
                if current is None or _assignment_precedence(assignment, current):
                    winning_assignment_by_thread[assignment.conversation_thread_id] = assignment
            if assignment.sales_case_id is not None:
                current = winning_assignment_by_sales_case.get(assignment.sales_case_id)
                if current is None or _assignment_precedence(assignment, current):
                    winning_assignment_by_sales_case[assignment.sales_case_id] = assignment

        attributed: dict[UUID, UUID] = {}
        for thread_id in thread_ids:
            thread = threads_by_id.get(thread_id)
            if thread is None:
                continue
            thread_assignment = winning_assignment_by_thread.get(thread_id)
            if thread_assignment is not None:
                attributed[thread_id] = thread_assignment.manager_user_id
                continue
            if thread.sales_case_id is not None:
                case_assignment = winning_assignment_by_sales_case.get(thread.sales_case_id)
                if case_assignment is not None:
                    attributed[thread_id] = case_assignment.manager_user_id
        return attributed

    def _calculate_values(
        self,
        *,
        messages: tuple[MetricsMessageRow, ...],
        thread_ids: set[UUID],
        source_data: MetricsSourceData,
    ) -> tuple[MetricValue, ...]:
        inbound_messages = tuple(
            message
            for message in messages
            if message.direction is MessageDirection.INBOUND
            and message.sender_type is ParticipantSenderType.CUSTOMER
        )
        outbound_manager_messages = tuple(
            message
            for message in messages
            if message.direction is MessageDirection.OUTBOUND
            and message.sender_type is ParticipantSenderType.MANAGER
        )
        inbound_threads = {message.conversation_thread_id for message in inbound_messages}
        response_latencies: list[int] = []
        responded_threads: set[UUID] = set()
        messages_by_thread: dict[UUID, list[MetricsMessageRow]] = defaultdict(list)
        for message in messages:
            messages_by_thread[message.conversation_thread_id].append(message)
        for thread_id, thread_messages in messages_by_thread.items():
            ordered = sorted(thread_messages, key=lambda item: (item.received_at, str(item.id)))
            earliest_inbound = next(
                (
                    item
                    for item in ordered
                    if item.direction is MessageDirection.INBOUND
                    and item.sender_type is ParticipantSenderType.CUSTOMER
                ),
                None,
            )
            if earliest_inbound is None:
                continue
            earliest_response = next(
                (
                    item
                    for item in ordered
                    if item.received_at > earliest_inbound.received_at
                    and item.direction is MessageDirection.OUTBOUND
                    and item.sender_type is ParticipantSenderType.MANAGER
                ),
                None,
            )
            if earliest_response is None:
                continue
            latency = int(
                (earliest_response.received_at - earliest_inbound.received_at).total_seconds()
            )
            if latency < 0:
                continue
            responded_threads.add(thread_id)
            response_latencies.append(latency)

        unresponded_threads = inbound_threads - responded_threads
        response_rate = floor_basis_points(
            numerator=len(responded_threads),
            denominator=len(inbound_threads),
        )
        median = deterministic_median_seconds(tuple(response_latencies))
        p90 = deterministic_p90_seconds(tuple(response_latencies))

        failed_delivery_count = sum(
            1
            for event in source_data.delivery_events
            if event.conversation_thread_id in thread_ids and event.status is DeliveryStatus.FAILED
        )
        appointment_booked_count = sum(
            1
            for sales_case in source_data.sales_cases
            if sales_case.status is SalesCaseStatus.APPOINTMENT_BOOKED
        )
        won_count = sum(
            1 for outcome in source_data.crm_outcomes if outcome.outcome_type is CrmOutcomeType.WON
        )
        lost_count = sum(
            1 for outcome in source_data.crm_outcomes if outcome.outcome_type is CrmOutcomeType.LOST
        )
        conversion = floor_basis_points(numerator=won_count, denominator=won_count + lost_count)

        values: list[MetricValue] = [
            MetricValue(MetricKey.INBOUND_MESSAGE_COUNT, len(inbound_messages)),
            MetricValue(MetricKey.OUTBOUND_MANAGER_MESSAGE_COUNT, len(outbound_manager_messages)),
            MetricValue(MetricKey.ACTIVE_THREAD_COUNT, len(thread_ids)),
            MetricValue(MetricKey.INBOUND_THREAD_COUNT, len(inbound_threads)),
            MetricValue(MetricKey.RESPONDED_THREAD_COUNT, len(responded_threads)),
            MetricValue(MetricKey.UNRESPONDED_THREAD_COUNT, len(unresponded_threads)),
            MetricValue(MetricKey.FIRST_RESPONSE_SAMPLE_COUNT, len(response_latencies)),
            MetricValue(MetricKey.FAILED_DELIVERY_COUNT, failed_delivery_count),
            MetricValue(MetricKey.APPOINTMENT_BOOKED_CASE_COUNT, appointment_booked_count),
            MetricValue(MetricKey.WON_CASE_COUNT, won_count),
            MetricValue(MetricKey.LOST_CASE_COUNT, lost_count),
        ]
        if response_rate is not None:
            values.append(
                MetricValue(
                    MetricKey.RESPONSE_RATE_BASIS_POINTS,
                    response_rate,
                    numerator=len(responded_threads),
                    denominator=len(inbound_threads),
                )
            )
        if median is not None:
            values.append(MetricValue(MetricKey.MEDIAN_FIRST_RESPONSE_SECONDS, median))
        if p90 is not None:
            values.append(MetricValue(MetricKey.P90_FIRST_RESPONSE_SECONDS, p90))
        if conversion is not None:
            values.append(
                MetricValue(
                    MetricKey.CONVERSION_RATE_BASIS_POINTS,
                    conversion,
                    numerator=won_count,
                    denominator=won_count + lost_count,
                )
            )
        return tuple(values)


def _assignment_precedence(
    candidate: MetricsAssignmentRow,
    current: MetricsAssignmentRow,
) -> bool:
    if candidate.assigned_at != current.assigned_at:
        return candidate.assigned_at > current.assigned_at
    return str(candidate.id) > str(current.id)
