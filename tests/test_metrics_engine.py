"""Unit tests for deterministic metrics calculation engine (Block LM)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from closeros.application.metrics_engine import MetricsEngine
from closeros.application.metrics_source_data import (
    MetricsAssignmentRow,
    MetricsCrmOutcomeRow,
    MetricsDeliveryEventRow,
    MetricsMessageRow,
    MetricsSalesCaseRow,
    MetricsSourceData,
    MetricsThreadRow,
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
    MetricSnapshotStatus,
    MetricValue,
    MetricWindow,
    deterministic_median_seconds,
    deterministic_p90_seconds,
    floor_basis_points,
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("00000000-0000-0000-0000-000000000010")
MANAGER_A = UUID("00000000-0000-0000-0000-000000000020")
MANAGER_B = UUID("00000000-0000-0000-0000-000000000021")
THREAD_A = UUID("00000000-0000-0000-0000-000000000100")
THREAD_B = UUID("00000000-0000-0000-0000-000000000101")
THREAD_C = UUID("00000000-0000-0000-0000-000000000102")
SALES_CASE_A = UUID("00000000-0000-0000-0000-000000000200")
MESSAGE_BASE = UUID("00000000-0000-0000-0000-000000001000")
ASSIGNMENT_BASE = UUID("00000000-0000-0000-0000-000000002000")

WINDOW_START = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 7, 2, 0, 0, tzinfo=UTC)
COMPUTED_AT = datetime(2026, 7, 2, 1, 0, tzinfo=UTC)
WATERMARK = datetime(2026, 7, 2, 0, 30, tzinfo=UTC)


def _window() -> MetricWindow:
    return MetricWindow(
        start=WINDOW_START,
        end=WINDOW_END,
        window_code="daily_2026-07-01",
    )


def _message(
    *,
    index: int,
    thread_id: UUID,
    sender_type: ParticipantSenderType,
    direction: MessageDirection,
    received_at: datetime,
) -> MetricsMessageRow:
    return MetricsMessageRow(
        id=UUID(int=MESSAGE_BASE.int + index),
        tenant_id=TENANT_ID,
        conversation_thread_id=thread_id,
        sender_type=sender_type,
        direction=direction,
        received_at=received_at,
    )


def _value(snapshot_values: tuple[MetricValue, ...], key: MetricKey) -> int | None:
    for metric in snapshot_values:
        if metric.key is key:
            return metric.value
    return None


def _metric(snapshot_values: tuple[MetricValue, ...], key: MetricKey) -> MetricValue | None:
    for metric in snapshot_values:
        if metric.key is key:
            return metric
    return None


def _basic_source(
    *,
    messages: tuple[MetricsMessageRow, ...],
    threads: tuple[MetricsThreadRow, ...] | None = None,
    assignments: tuple[MetricsAssignmentRow, ...] = (),
    delivery_events: tuple[MetricsDeliveryEventRow, ...] = (),
    sales_cases: tuple[MetricsSalesCaseRow, ...] = (),
    crm_outcomes: tuple[MetricsCrmOutcomeRow, ...] = (),
) -> MetricsSourceData:
    if threads is None:
        thread_ids = {message.conversation_thread_id for message in messages}
        threads = tuple(
            MetricsThreadRow(id=thread_id, tenant_id=TENANT_ID, sales_case_id=None)
            for thread_id in sorted(thread_ids, key=str)
        )
    return MetricsSourceData(
        messages=messages,
        threads=threads,
        delivery_events=delivery_events,
        sales_cases=sales_cases,
        crm_outcomes=crm_outcomes,
        assignments=assignments,
        watermark=WATERMARK,
    )


def test_floor_basis_points_computes_integer_floor() -> None:
    assert floor_basis_points(numerator=3, denominator=4) == 7500


def test_floor_basis_points_returns_none_for_zero_denominator() -> None:
    assert floor_basis_points(numerator=1, denominator=0) is None


def test_deterministic_median_seconds_even_count() -> None:
    assert deterministic_median_seconds((100, 200, 300, 400)) == 250


def test_deterministic_median_seconds_odd_count() -> None:
    assert deterministic_median_seconds((100, 200, 300)) == 200


def test_deterministic_p90_seconds_nearest_rank() -> None:
    assert deterministic_p90_seconds((10, 20, 30, 40, 50, 60, 70, 80, 90, 100)) == 90


def test_inbound_count_includes_customer_inbound_only() -> None:
    t0 = WINDOW_START + timedelta(hours=1)
    messages = (
        _message(
            index=1,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
        _message(
            index=2,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.MANAGER,
            direction=MessageDirection.OUTBOUND,
            received_at=t0 + timedelta(minutes=1),
        ),
        _message(
            index=3,
            thread_id=THREAD_B,
            sender_type=ParticipantSenderType.BOT,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
        _message(
            index=4,
            thread_id=THREAD_B,
            sender_type=ParticipantSenderType.BOT,
            direction=MessageDirection.OUTBOUND,
            received_at=t0 + timedelta(minutes=1),
        ),
    )
    engine = MetricsEngine()
    snapshot = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.TENANT,
        manager_user_id=None,
        window=_window(),
        source_data=_basic_source(messages=messages),
        computed_at=COMPUTED_AT,
    )
    assert _value(snapshot.values, MetricKey.INBOUND_MESSAGE_COUNT) == 1
    assert _value(snapshot.values, MetricKey.OUTBOUND_MANAGER_MESSAGE_COUNT) == 1


def test_response_rate_omitted_when_no_inbound_threads() -> None:
    engine = MetricsEngine()
    snapshot = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.TENANT,
        manager_user_id=None,
        window=_window(),
        source_data=_basic_source(messages=()),
        computed_at=COMPUTED_AT,
    )
    assert _value(snapshot.values, MetricKey.RESPONSE_RATE_BASIS_POINTS) is None
    assert _value(snapshot.values, MetricKey.INBOUND_THREAD_COUNT) == 0


def test_response_rate_and_latency_metrics() -> None:
    t0 = WINDOW_START + timedelta(hours=2)
    messages = (
        _message(
            index=1,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
        _message(
            index=2,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.MANAGER,
            direction=MessageDirection.OUTBOUND,
            received_at=t0 + timedelta(seconds=100),
        ),
        _message(
            index=3,
            thread_id=THREAD_B,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
        _message(
            index=4,
            thread_id=THREAD_B,
            sender_type=ParticipantSenderType.MANAGER,
            direction=MessageDirection.OUTBOUND,
            received_at=t0 + timedelta(seconds=300),
        ),
        _message(
            index=5,
            thread_id=THREAD_C,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
    )
    engine = MetricsEngine()
    snapshot = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.TENANT,
        manager_user_id=None,
        window=_window(),
        source_data=_basic_source(messages=messages),
        computed_at=COMPUTED_AT,
    )
    response_metric = _metric(snapshot.values, MetricKey.RESPONSE_RATE_BASIS_POINTS)
    assert response_metric is not None
    assert response_metric.value == 6666
    assert response_metric.numerator == 2
    assert response_metric.denominator == 3
    assert _value(snapshot.values, MetricKey.UNRESPONDED_THREAD_COUNT) == 1
    assert _value(snapshot.values, MetricKey.MEDIAN_FIRST_RESPONSE_SECONDS) == 200
    assert _value(snapshot.values, MetricKey.P90_FIRST_RESPONSE_SECONDS) == 300


def test_conversion_rate_basis_points() -> None:
    outcomes = (
        MetricsCrmOutcomeRow(
            sales_case_id=SALES_CASE_A,
            outcome_type=CrmOutcomeType.WON,
            occurred_at=WINDOW_START + timedelta(hours=3),
        ),
        MetricsCrmOutcomeRow(
            sales_case_id=UUID(int=SALES_CASE_A.int + 1),
            outcome_type=CrmOutcomeType.LOST,
            occurred_at=WINDOW_START + timedelta(hours=4),
        ),
        MetricsCrmOutcomeRow(
            sales_case_id=UUID(int=SALES_CASE_A.int + 2),
            outcome_type=CrmOutcomeType.LOST,
            occurred_at=WINDOW_START + timedelta(hours=5),
        ),
    )
    engine = MetricsEngine()
    snapshot = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.TENANT,
        manager_user_id=None,
        window=_window(),
        source_data=_basic_source(messages=(), crm_outcomes=outcomes),
        computed_at=COMPUTED_AT,
    )
    conversion = _metric(snapshot.values, MetricKey.CONVERSION_RATE_BASIS_POINTS)
    assert conversion is not None
    assert conversion.value == 3333
    assert conversion.numerator == 1
    assert conversion.denominator == 3


def test_conversion_rate_omitted_without_closed_outcomes() -> None:
    engine = MetricsEngine()
    snapshot = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.TENANT,
        manager_user_id=None,
        window=_window(),
        source_data=_basic_source(messages=(), crm_outcomes=()),
        computed_at=COMPUTED_AT,
    )
    assert _value(snapshot.values, MetricKey.CONVERSION_RATE_BASIS_POINTS) is None


def test_manager_scope_uses_direct_thread_assignment() -> None:
    t0 = WINDOW_START + timedelta(hours=1)
    messages = (
        _message(
            index=1,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
        _message(
            index=2,
            thread_id=THREAD_B,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
    )
    assignments = (
        MetricsAssignmentRow(
            id=ASSIGNMENT_BASE,
            tenant_id=TENANT_ID,
            manager_user_id=MANAGER_A,
            conversation_thread_id=THREAD_A,
            sales_case_id=None,
            assigned_at=t0 - timedelta(days=1),
        ),
    )
    engine = MetricsEngine()
    snapshot = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.MANAGER,
        manager_user_id=MANAGER_A,
        window=_window(),
        source_data=_basic_source(messages=messages, assignments=assignments),
        computed_at=COMPUTED_AT,
    )
    assert _value(snapshot.values, MetricKey.ACTIVE_THREAD_COUNT) == 1
    assert _value(snapshot.values, MetricKey.INBOUND_MESSAGE_COUNT) == 1


def test_manager_scope_falls_back_to_sales_case_assignment() -> None:
    t0 = WINDOW_START + timedelta(hours=1)
    threads = (
        MetricsThreadRow(id=THREAD_A, tenant_id=TENANT_ID, sales_case_id=SALES_CASE_A),
        MetricsThreadRow(id=THREAD_B, tenant_id=TENANT_ID, sales_case_id=None),
    )
    messages = (
        _message(
            index=1,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
        _message(
            index=2,
            thread_id=THREAD_B,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
    )
    assignments = (
        MetricsAssignmentRow(
            id=ASSIGNMENT_BASE,
            tenant_id=TENANT_ID,
            manager_user_id=MANAGER_A,
            conversation_thread_id=None,
            sales_case_id=SALES_CASE_A,
            assigned_at=t0 - timedelta(days=1),
        ),
    )
    engine = MetricsEngine()
    snapshot = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.MANAGER,
        manager_user_id=MANAGER_A,
        window=_window(),
        source_data=_basic_source(
            messages=messages,
            threads=threads,
            assignments=assignments,
        ),
        computed_at=COMPUTED_AT,
    )
    assert _value(snapshot.values, MetricKey.ACTIVE_THREAD_COUNT) == 1


def test_manager_assignment_tie_break_prefers_newer_assigned_at() -> None:
    t0 = WINDOW_START + timedelta(hours=1)
    messages = (
        _message(
            index=1,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
    )
    assignments = (
        MetricsAssignmentRow(
            id=UUID(int=ASSIGNMENT_BASE.int + 1),
            tenant_id=TENANT_ID,
            manager_user_id=MANAGER_A,
            conversation_thread_id=THREAD_A,
            sales_case_id=None,
            assigned_at=t0 - timedelta(days=2),
        ),
        MetricsAssignmentRow(
            id=ASSIGNMENT_BASE,
            tenant_id=TENANT_ID,
            manager_user_id=MANAGER_B,
            conversation_thread_id=THREAD_A,
            sales_case_id=None,
            assigned_at=t0 - timedelta(days=1),
        ),
    )
    engine = MetricsEngine()
    snapshot_b = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.MANAGER,
        manager_user_id=MANAGER_B,
        window=_window(),
        source_data=_basic_source(messages=messages, assignments=assignments),
        computed_at=COMPUTED_AT,
    )
    snapshot_a = engine.calculate_snapshot(
        snapshot_id=UUID(int=SNAPSHOT_ID.int + 1),
        tenant_id=TENANT_ID,
        scope=MetricScope.MANAGER,
        manager_user_id=MANAGER_A,
        window=_window(),
        source_data=_basic_source(messages=messages, assignments=assignments),
        computed_at=COMPUTED_AT,
    )
    assert _value(snapshot_b.values, MetricKey.ACTIVE_THREAD_COUNT) == 1
    assert _value(snapshot_a.values, MetricKey.ACTIVE_THREAD_COUNT) == 0


def test_manager_assignment_tie_break_uses_higher_id_when_assigned_at_equal() -> None:
    t0 = WINDOW_START + timedelta(hours=1)
    assigned_at = t0 - timedelta(days=1)
    messages = (
        _message(
            index=1,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
    )
    lower_id = ASSIGNMENT_BASE
    higher_id = UUID(int=ASSIGNMENT_BASE.int + 1)
    assignments = (
        MetricsAssignmentRow(
            id=lower_id,
            tenant_id=TENANT_ID,
            manager_user_id=MANAGER_A,
            conversation_thread_id=THREAD_A,
            sales_case_id=None,
            assigned_at=assigned_at,
        ),
        MetricsAssignmentRow(
            id=higher_id,
            tenant_id=TENANT_ID,
            manager_user_id=MANAGER_B,
            conversation_thread_id=THREAD_A,
            sales_case_id=None,
            assigned_at=assigned_at,
        ),
    )
    engine = MetricsEngine()
    snapshot_b = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.MANAGER,
        manager_user_id=MANAGER_B,
        window=_window(),
        source_data=_basic_source(messages=messages, assignments=assignments),
        computed_at=COMPUTED_AT,
    )
    assert _value(snapshot_b.values, MetricKey.ACTIVE_THREAD_COUNT) == 1


def test_failed_delivery_count_scoped_to_active_threads() -> None:
    t0 = WINDOW_START + timedelta(hours=1)
    messages = (
        _message(
            index=1,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
    )
    delivery_events = (
        MetricsDeliveryEventRow(
            conversation_thread_id=THREAD_A,
            message_id=UUID(int=MESSAGE_BASE.int + 1),
            status=DeliveryStatus.FAILED,
            occurred_at=t0 + timedelta(minutes=1),
        ),
        MetricsDeliveryEventRow(
            conversation_thread_id=THREAD_B,
            message_id=UUID(int=MESSAGE_BASE.int + 2),
            status=DeliveryStatus.FAILED,
            occurred_at=t0 + timedelta(minutes=2),
        ),
    )
    assignments = (
        MetricsAssignmentRow(
            id=ASSIGNMENT_BASE,
            tenant_id=TENANT_ID,
            manager_user_id=MANAGER_A,
            conversation_thread_id=THREAD_A,
            sales_case_id=None,
            assigned_at=t0 - timedelta(days=1),
        ),
    )
    engine = MetricsEngine()
    snapshot = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.MANAGER,
        manager_user_id=MANAGER_A,
        window=_window(),
        source_data=_basic_source(
            messages=messages,
            delivery_events=delivery_events,
            assignments=assignments,
        ),
        computed_at=COMPUTED_AT,
    )
    assert _value(snapshot.values, MetricKey.FAILED_DELIVERY_COUNT) == 1


def test_half_open_window_semantics_via_pre_filtered_source_data() -> None:
    """Loader supplies rows where start <= received_at < end (half-open interval)."""
    at_start = WINDOW_START
    before_start = WINDOW_START - timedelta(seconds=1)
    at_end_exclusive = WINDOW_END
    messages_all = (
        _message(
            index=1,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=before_start,
        ),
        _message(
            index=2,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=at_start,
        ),
        _message(
            index=3,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=at_end_exclusive,
        ),
    )
    included = tuple(
        message for message in messages_all if WINDOW_START <= message.received_at < WINDOW_END
    )
    engine = MetricsEngine()
    snapshot = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.TENANT,
        manager_user_id=None,
        window=_window(),
        source_data=_basic_source(messages=included),
        computed_at=COMPUTED_AT,
    )
    assert _value(snapshot.values, MetricKey.INBOUND_MESSAGE_COUNT) == 1


def test_snapshot_metadata_fields() -> None:
    sales_cases = (
        MetricsSalesCaseRow(
            id=SALES_CASE_A,
            tenant_id=TENANT_ID,
            status=SalesCaseStatus.APPOINTMENT_BOOKED,
            updated_at=WINDOW_START + timedelta(hours=2),
        ),
    )
    engine = MetricsEngine()
    snapshot = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.TENANT,
        manager_user_id=None,
        window=_window(),
        source_data=_basic_source(messages=(), sales_cases=sales_cases),
        computed_at=COMPUTED_AT,
    )
    assert snapshot.formula_version == METRIC_FORMULA_VERSION
    assert snapshot.status is MetricSnapshotStatus.COMPLETED
    assert snapshot.source_watermark == WATERMARK
    assert _value(snapshot.values, MetricKey.APPOINTMENT_BOOKED_CASE_COUNT) == 1


def test_manager_crm_outcomes_are_isolated_between_managers() -> None:
    t0 = WINDOW_START + timedelta(hours=1)
    case_a = SALES_CASE_A
    case_b = UUID(int=SALES_CASE_A.int + 1)
    case_a_appt = UUID(int=SALES_CASE_A.int + 2)
    case_b_appt = UUID(int=SALES_CASE_A.int + 3)
    threads = (
        MetricsThreadRow(id=THREAD_A, tenant_id=TENANT_ID, sales_case_id=case_a),
        MetricsThreadRow(id=THREAD_B, tenant_id=TENANT_ID, sales_case_id=case_b),
        MetricsThreadRow(id=THREAD_C, tenant_id=TENANT_ID, sales_case_id=case_a_appt),
    )
    messages = (
        _message(
            index=1,
            thread_id=THREAD_A,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
        _message(
            index=2,
            thread_id=THREAD_B,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
        _message(
            index=3,
            thread_id=THREAD_C,
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            received_at=t0,
        ),
    )
    sales_cases = (
        MetricsSalesCaseRow(
            id=case_a,
            tenant_id=TENANT_ID,
            status=SalesCaseStatus.WON,
            updated_at=t0,
        ),
        MetricsSalesCaseRow(
            id=case_b,
            tenant_id=TENANT_ID,
            status=SalesCaseStatus.LOST,
            updated_at=t0,
        ),
        MetricsSalesCaseRow(
            id=case_a_appt,
            tenant_id=TENANT_ID,
            status=SalesCaseStatus.APPOINTMENT_BOOKED,
            updated_at=t0,
        ),
        MetricsSalesCaseRow(
            id=case_b_appt,
            tenant_id=TENANT_ID,
            status=SalesCaseStatus.APPOINTMENT_BOOKED,
            updated_at=t0,
        ),
    )
    crm_outcomes = (
        MetricsCrmOutcomeRow(
            sales_case_id=case_a,
            outcome_type=CrmOutcomeType.WON,
            occurred_at=t0 + timedelta(hours=1),
        ),
        MetricsCrmOutcomeRow(
            sales_case_id=case_b,
            outcome_type=CrmOutcomeType.LOST,
            occurred_at=t0 + timedelta(hours=1),
        ),
    )
    assignments = (
        MetricsAssignmentRow(
            id=ASSIGNMENT_BASE,
            tenant_id=TENANT_ID,
            manager_user_id=MANAGER_A,
            conversation_thread_id=THREAD_A,
            sales_case_id=None,
            assigned_at=t0 - timedelta(days=1),
        ),
        MetricsAssignmentRow(
            id=UUID(int=ASSIGNMENT_BASE.int + 1),
            tenant_id=TENANT_ID,
            manager_user_id=MANAGER_B,
            conversation_thread_id=THREAD_B,
            sales_case_id=None,
            assigned_at=t0 - timedelta(days=1),
        ),
        MetricsAssignmentRow(
            id=UUID(int=ASSIGNMENT_BASE.int + 2),
            tenant_id=TENANT_ID,
            manager_user_id=MANAGER_A,
            conversation_thread_id=THREAD_C,
            sales_case_id=None,
            assigned_at=t0 - timedelta(days=1),
        ),
        MetricsAssignmentRow(
            id=UUID(int=ASSIGNMENT_BASE.int + 3),
            tenant_id=TENANT_ID,
            manager_user_id=MANAGER_B,
            conversation_thread_id=None,
            sales_case_id=case_b_appt,
            assigned_at=t0 - timedelta(days=1),
        ),
    )
    source = _basic_source(
        messages=messages,
        threads=threads,
        sales_cases=sales_cases,
        crm_outcomes=crm_outcomes,
        assignments=assignments,
    )
    engine = MetricsEngine()
    snapshot_a = engine.calculate_snapshot(
        snapshot_id=SNAPSHOT_ID,
        tenant_id=TENANT_ID,
        scope=MetricScope.MANAGER,
        manager_user_id=MANAGER_A,
        window=_window(),
        source_data=source,
        computed_at=COMPUTED_AT,
    )
    snapshot_b = engine.calculate_snapshot(
        snapshot_id=UUID(int=SNAPSHOT_ID.int + 1),
        tenant_id=TENANT_ID,
        scope=MetricScope.MANAGER,
        manager_user_id=MANAGER_B,
        window=_window(),
        source_data=source,
        computed_at=COMPUTED_AT,
    )
    snapshot_tenant = engine.calculate_snapshot(
        snapshot_id=UUID(int=SNAPSHOT_ID.int + 2),
        tenant_id=TENANT_ID,
        scope=MetricScope.TENANT,
        manager_user_id=None,
        window=_window(),
        source_data=source,
        computed_at=COMPUTED_AT,
    )
    assert _value(snapshot_a.values, MetricKey.WON_CASE_COUNT) == 1
    assert _value(snapshot_a.values, MetricKey.LOST_CASE_COUNT) == 0
    assert _value(snapshot_a.values, MetricKey.APPOINTMENT_BOOKED_CASE_COUNT) == 1
    assert _value(snapshot_b.values, MetricKey.WON_CASE_COUNT) == 0
    assert _value(snapshot_b.values, MetricKey.LOST_CASE_COUNT) == 1
    assert _value(snapshot_b.values, MetricKey.APPOINTMENT_BOOKED_CASE_COUNT) == 1
    assert _value(snapshot_tenant.values, MetricKey.WON_CASE_COUNT) == 1
    assert _value(snapshot_tenant.values, MetricKey.LOST_CASE_COUNT) == 1
    assert _value(snapshot_tenant.values, MetricKey.APPOINTMENT_BOOKED_CASE_COUNT) == 2
