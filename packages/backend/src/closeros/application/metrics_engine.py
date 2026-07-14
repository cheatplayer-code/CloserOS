"""Deterministic tenant and manager metrics calculation engine."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from closeros.application.manager_attribution import resolve_manager_metric_scope
from closeros.application.metrics_source_data import (
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
        thread_ids, sales_case_ids = self._scope_ids(
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
            sales_case_ids=sales_case_ids,
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

    def _scope_ids(
        self,
        *,
        source_data: MetricsSourceData,
        scope: MetricScope,
        manager_user_id: UUID | None,
        window_end: datetime,
    ) -> tuple[set[UUID], set[UUID]]:
        if scope is MetricScope.TENANT:
            all_thread_ids = {thread.id for thread in source_data.threads}
            all_sales_case_ids = {case.id for case in source_data.sales_cases}
            for thread in source_data.threads:
                if thread.sales_case_id is not None:
                    all_sales_case_ids.add(thread.sales_case_id)
            for outcome in source_data.crm_outcomes:
                all_sales_case_ids.add(outcome.sales_case_id)
            return all_thread_ids, all_sales_case_ids
        if manager_user_id is None:
            return set(), set()
        attributed = resolve_manager_metric_scope(
            source_data=source_data,
            manager_user_id=manager_user_id,
            window_end=window_end,
        )
        return set(attributed.thread_ids), set(attributed.sales_case_ids)

    def _calculate_values(
        self,
        *,
        messages: tuple[MetricsMessageRow, ...],
        thread_ids: set[UUID],
        sales_case_ids: set[UUID],
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
            if sales_case.id in sales_case_ids
            and sales_case.status is SalesCaseStatus.APPOINTMENT_BOOKED
        )
        won_count = sum(
            1
            for outcome in source_data.crm_outcomes
            if outcome.sales_case_id in sales_case_ids
            and outcome.outcome_type is CrmOutcomeType.WON
        )
        lost_count = sum(
            1
            for outcome in source_data.crm_outcomes
            if outcome.sales_case_id in sales_case_ids
            and outcome.outcome_type is CrmOutcomeType.LOST
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
