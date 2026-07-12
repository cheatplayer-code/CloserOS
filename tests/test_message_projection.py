"""Tests for deterministic message projection edge cases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from closeros.domain.canonical_enums import DeliveryStatus
from closeros.domain.message_projection import project_message

from tests.canonical_persistence_support import (
    CONTENT_A_ID,
    CONTENT_B_ID,
    DELETION_EVENT_A_ID,
    DELIVERY_EVENT_A_ID,
    EDIT_EVENT_A_ID,
    MESSAGE_A_ID,
    synthetic_message,
    synthetic_message_deletion_event,
    synthetic_message_delivery_status_event,
    synthetic_message_edit_event,
)
from tests.tenant_persistence_support import TENANT_A_ID

NOW = datetime(2026, 7, 12, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)
EVEN_LATER = NOW + timedelta(minutes=10)
LATEST = NOW + timedelta(minutes=15)


def test_projection_without_events_preserves_original_content() -> None:
    message = synthetic_message()

    projection = project_message(message)

    assert projection.message_id == MESSAGE_A_ID
    assert projection.tenant_id == TENANT_A_ID
    assert projection.content_id == CONTENT_A_ID
    assert projection.is_deleted is False
    assert projection.deleted_at is None
    assert projection.delivery_status is None
    assert projection.delivery_status_at is None


def test_projection_applies_latest_edit_event_content() -> None:
    message = synthetic_message()
    first_edit = synthetic_message_edit_event(
        event_id=EDIT_EVENT_A_ID,
        external_event_id="edit-first",
        content_id=UUID("00000000-0000-0000-0000-000000000b01"),
        occurred_at=LATER,
    )
    second_edit = synthetic_message_edit_event(
        event_id=UUID("00000000-0000-0000-0000-000000000602"),
        external_event_id="edit-second",
        content_id=CONTENT_B_ID,
        occurred_at=EVEN_LATER,
    )

    projection = project_message(
        message,
        edit_events=(second_edit, first_edit),
    )

    assert projection.content_id == CONTENT_B_ID


def test_projection_deduplicates_edit_events_by_external_event_id() -> None:
    message = synthetic_message()
    duplicate = synthetic_message_edit_event(
        external_event_id="edit-dup",
        content_id=CONTENT_B_ID,
        occurred_at=LATER,
    )
    replay = synthetic_message_edit_event(
        event_id=UUID("00000000-0000-0000-0000-000000000603"),
        external_event_id="edit-dup",
        content_id=UUID("00000000-0000-0000-0000-000000000b02"),
        occurred_at=EVEN_LATER,
    )

    projection = project_message(message, edit_events=(duplicate, replay))

    assert projection.content_id == CONTENT_B_ID


def test_projection_marks_message_deleted_from_deletion_events() -> None:
    message = synthetic_message()
    deletion = synthetic_message_deletion_event(occurred_at=LATER)

    projection = project_message(message, deletion_events=(deletion,))

    assert projection.is_deleted is True
    assert projection.deleted_at == LATER


def test_projection_uses_latest_delivery_status_event() -> None:
    message = synthetic_message()
    first = synthetic_message_delivery_status_event(
        external_event_id="delivery-first",
        delivery_status=DeliveryStatus.SENT,
        occurred_at=LATER,
    )
    second = synthetic_message_delivery_status_event(
        event_id=UUID("00000000-0000-0000-0000-000000000604"),
        external_event_id="delivery-second",
        delivery_status=DeliveryStatus.READ,
        occurred_at=EVEN_LATER,
    )

    projection = project_message(message, delivery_status_events=(first, second))

    assert projection.delivery_status is DeliveryStatus.READ
    assert projection.delivery_status_at == EVEN_LATER


def test_projection_rejects_cross_tenant_events() -> None:
    message = synthetic_message()
    foreign_tenant_id = UUID("00000000-0000-0000-0000-000000000999")
    foreign_edit = synthetic_message_edit_event(tenant_id=foreign_tenant_id)

    with pytest.raises(ValueError, match="same tenant"):
        project_message(message, edit_events=(foreign_edit,))


def test_projection_rejects_events_for_different_message() -> None:
    message = synthetic_message()
    foreign_edit = synthetic_message_edit_event(
        message_id=UUID("00000000-0000-0000-0000-000000000999"),
    )

    with pytest.raises(ValueError, match="projected message"):
        project_message(message, edit_events=(foreign_edit,))


def test_projection_combines_edit_deletion_and_delivery_events() -> None:
    message = synthetic_message()
    edit = synthetic_message_edit_event(content_id=CONTENT_B_ID, occurred_at=LATER)
    deletion = synthetic_message_deletion_event(
        event_id=DELETION_EVENT_A_ID,
        occurred_at=EVEN_LATER,
    )
    delivery = synthetic_message_delivery_status_event(
        event_id=DELIVERY_EVENT_A_ID,
        occurred_at=LATEST,
        delivery_status=DeliveryStatus.DELIVERED,
    )

    projection = project_message(
        message,
        edit_events=(edit,),
        deletion_events=(deletion,),
        delivery_status_events=(delivery,),
    )

    assert projection.content_id == CONTENT_B_ID
    assert projection.is_deleted is True
    assert projection.deleted_at == EVEN_LATER
    assert projection.delivery_status is DeliveryStatus.DELIVERED
    assert projection.delivery_status_at == LATEST


def test_projection_deduplicates_deletion_events_by_external_event_id() -> None:
    message = synthetic_message()
    first = synthetic_message_deletion_event(
        external_event_id="delete-dup",
        occurred_at=LATER,
    )
    replay = synthetic_message_deletion_event(
        event_id=UUID("00000000-0000-0000-0000-000000000605"),
        external_event_id="delete-dup",
        occurred_at=EVEN_LATER,
    )

    projection = project_message(message, deletion_events=(first, replay))

    assert projection.is_deleted is True
    assert projection.deleted_at == LATER
