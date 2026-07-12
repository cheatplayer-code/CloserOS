"""Pure projection service for current message state."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.domain.canonical_enums import DeliveryStatus
from closeros.domain.message import Message
from closeros.domain.message_events import (
    MessageDeletionEvent,
    MessageDeliveryStatusEvent,
    MessageEditEvent,
)

MessageEvent = MessageEditEvent | MessageDeletionEvent | MessageDeliveryStatusEvent


def _deduplicate_events[T](
    events: Sequence[T],
    *,
    external_event_id: Callable[[T], str],
    sort_key: Callable[[T], tuple[datetime, UUID]],
) -> list[T]:
    deduplicated: list[T] = []
    seen_external_event_ids: set[str] = set()

    for event in sorted(events, key=sort_key):
        event_id = external_event_id(event)

        if event_id in seen_external_event_ids:
            continue

        seen_external_event_ids.add(event_id)
        deduplicated.append(event)

    return deduplicated


def _validate_message_scope(
    message: Message,
    *,
    edit_events: Sequence[MessageEditEvent],
    deletion_events: Sequence[MessageDeletionEvent],
    delivery_status_events: Sequence[MessageDeliveryStatusEvent],
) -> None:
    all_events: list[MessageEvent] = [
        *edit_events,
        *deletion_events,
        *delivery_status_events,
    ]

    for event in all_events:
        if event.tenant_id != message.tenant_id:
            raise ValueError("all events must belong to the same tenant as the message")

        if event.message_id != message.id:
            raise ValueError("all events must belong to the projected message")


@dataclass(frozen=True, slots=True)
class MessageProjection:
    message_id: UUID
    tenant_id: UUID
    content_id: UUID | None
    is_deleted: bool
    deleted_at: datetime | None
    delivery_status: DeliveryStatus | None
    delivery_status_at: datetime | None


def project_message(
    message: Message,
    *,
    edit_events: Sequence[MessageEditEvent] = (),
    deletion_events: Sequence[MessageDeletionEvent] = (),
    delivery_status_events: Sequence[MessageDeliveryStatusEvent] = (),
) -> MessageProjection:
    """Derive the current message state without mutating source events."""

    _validate_message_scope(
        message,
        edit_events=edit_events,
        deletion_events=deletion_events,
        delivery_status_events=delivery_status_events,
    )

    content_id = message.content_id

    for edit_event in _deduplicate_events(
        edit_events,
        external_event_id=lambda event: event.external_event_id,
        sort_key=lambda event: (event.occurred_at, event.id),
    ):
        content_id = edit_event.content_id

    deduplicated_deletions = _deduplicate_events(
        deletion_events,
        external_event_id=lambda event: event.external_event_id,
        sort_key=lambda event: (event.occurred_at, event.id),
    )
    is_deleted = bool(deduplicated_deletions)
    deleted_at = deduplicated_deletions[-1].occurred_at if is_deleted else None

    deduplicated_delivery_events = _deduplicate_events(
        delivery_status_events,
        external_event_id=lambda event: event.external_event_id,
        sort_key=lambda event: (event.occurred_at, event.id),
    )
    delivery_status = None
    delivery_status_at = None

    if deduplicated_delivery_events:
        latest_delivery_event = deduplicated_delivery_events[-1]
        delivery_status = latest_delivery_event.delivery_status
        delivery_status_at = latest_delivery_event.occurred_at

    return MessageProjection(
        message_id=message.id,
        tenant_id=message.tenant_id,
        content_id=content_id,
        is_deleted=is_deleted,
        deleted_at=deleted_at,
        delivery_status=delivery_status,
        delivery_status_at=delivery_status_at,
    )
