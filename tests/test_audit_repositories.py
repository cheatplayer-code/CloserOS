"""PostgreSQL repository tests for append-only audit events."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from closeros.application.audit_persistence import AuditQueryFilter
from closeros.domain.audit import AuditAction, AuditActorType, AuditScope, AuditTargetType
from sqlalchemy import make_url

from tests.conftest import _rebuild_database_url
from tests.test_audit_support import append_event, tenant_event

pytestmark = pytest.mark.auth_persistence

TENANT_A = UUID("00000000-0000-0000-0000-000000000010")
TENANT_B = UUID("00000000-0000-0000-0000-000000000011")
USER_ID = UUID("00000000-0000-0000-0000-000000000020")
NOW = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)


async def _append(
    uow_factory: Any,
    event: object,
) -> None:
    uow = uow_factory()
    async with uow:
        await uow.audit_events.append(event)
        await uow.commit()


def test_append_persists_audit_event(auth_audit_uow_factory: Any) -> None:
    event = tenant_event(tenant_id=TENANT_A, action=AuditAction.AUDIT_LOG_VIEWED)

    async def exercise() -> None:
        await _append(auth_audit_uow_factory, event)
        uow = auth_audit_uow_factory()
        async with uow:
            page = await uow.audit_events.query_page(
                query_filter=AuditQueryFilter(tenant_id=TENANT_A),
                cursor=None,
                page_size=10,
            )
        assert len(page.events) == 1
        assert page.events[0].id == event.id

    asyncio.run(exercise())


def test_query_orders_by_occurred_at_and_id_desc(auth_audit_uow_factory: Any) -> None:
    async def exercise() -> None:
        older = tenant_event(
            tenant_id=TENANT_A,
            occurred_at=NOW,
            event_id=UUID("00000000-0000-0000-0000-000000000001"),
        )
        newer = tenant_event(
            tenant_id=TENANT_A,
            occurred_at=NOW + timedelta(minutes=1),
            event_id=UUID("00000000-0000-0000-0000-000000000002"),
        )
        await _append(auth_audit_uow_factory, older)
        await _append(auth_audit_uow_factory, newer)
        uow = auth_audit_uow_factory()
        async with uow:
            page = await uow.audit_events.query_page(
                query_filter=AuditQueryFilter(tenant_id=TENANT_A),
                cursor=None,
                page_size=10,
            )
        assert [item.id for item in page.events] == [newer.id, older.id]

    asyncio.run(exercise())


def test_query_cursor_returns_next_page(auth_audit_uow_factory: Any) -> None:
    async def exercise() -> None:
        for index in range(3):
            await _append(
                auth_audit_uow_factory,
                tenant_event(
                    tenant_id=TENANT_A,
                    occurred_at=NOW + timedelta(minutes=index),
                    event_id=UUID(int=index + 1),
                ),
            )
        uow = auth_audit_uow_factory()
        async with uow:
            first = await uow.audit_events.query_page(
                query_filter=AuditQueryFilter(tenant_id=TENANT_A),
                cursor=None,
                page_size=2,
            )
            assert first.next_cursor is not None
            second = await uow.audit_events.query_page(
                query_filter=AuditQueryFilter(tenant_id=TENANT_A),
                cursor=first.next_cursor,
                page_size=2,
            )
        assert len(first.events) == 2
        assert len(second.events) == 1

    asyncio.run(exercise())


def test_query_filters_by_action_and_correlation(auth_audit_uow_factory: Any) -> None:
    correlation_id = uuid4()

    async def exercise() -> None:
        await _append(
            auth_audit_uow_factory,
            tenant_event(
                tenant_id=TENANT_A,
                action=AuditAction.TENANT_ACCESS_GRANTED,
                correlation_id=correlation_id,
            ),
        )
        await _append(
            auth_audit_uow_factory,
            tenant_event(
                tenant_id=TENANT_A,
                action=AuditAction.TENANT_ACCESS_DENIED,
                correlation_id=uuid4(),
            ),
        )
        uow = auth_audit_uow_factory()
        async with uow:
            page = await uow.audit_events.query_page(
                query_filter=AuditQueryFilter(
                    tenant_id=TENANT_A,
                    action=AuditAction.TENANT_ACCESS_GRANTED,
                    correlation_id=correlation_id,
                ),
                cursor=None,
                page_size=10,
            )
        assert len(page.events) == 1
        assert page.events[0].action is AuditAction.TENANT_ACCESS_GRANTED

    asyncio.run(exercise())


def test_query_is_tenant_isolated(auth_audit_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _append(auth_audit_uow_factory, tenant_event(tenant_id=TENANT_A))
        await _append(auth_audit_uow_factory, tenant_event(tenant_id=TENANT_B))
        uow = auth_audit_uow_factory()
        async with uow:
            page = await uow.audit_events.query_page(
                query_filter=AuditQueryFilter(tenant_id=TENANT_A),
                cursor=None,
                page_size=10,
            )
        assert len(page.events) == 1
        assert page.events[0].tenant_id == TENANT_A

    asyncio.run(exercise())


def test_transaction_rollback_discards_uncommitted_audit_events(
    auth_audit_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = auth_audit_uow_factory()
        async with uow:
            await uow.audit_events.append(tenant_event(tenant_id=TENANT_A))
            await uow.rollback()
        uow = auth_audit_uow_factory()
        async with uow:
            page = await uow.audit_events.query_page(
                query_filter=AuditQueryFilter(tenant_id=TENANT_A),
                cursor=None,
                page_size=10,
            )
        assert page.events == ()

    asyncio.run(exercise())


def test_database_trigger_rejects_update_and_delete(
    auth_test_database_url: str,
    auth_audit_uow_factory: Any,
) -> None:
    event = tenant_event(tenant_id=TENANT_A)
    asyncio.run(_append(auth_audit_uow_factory, event))

    direct_url = _rebuild_database_url(
        auth_test_database_url,
        database=make_url(auth_test_database_url).database or "postgres",
        sqlalchemy=False,
    )
    with psycopg.connect(direct_url) as connection:
        with pytest.raises(psycopg.errors.RaiseException):
            connection.execute(
                "UPDATE audit_events SET action = %s WHERE id = %s",
                ("auth.login.failed", event.id),
            )
        connection.rollback()
        with pytest.raises(psycopg.errors.RaiseException):
            connection.execute("DELETE FROM audit_events WHERE id = %s", (event.id,))


def test_global_event_persists_without_tenant(
    auth_test_database_url: str,
    auth_audit_uow_factory: Any,
) -> None:
    event = append_event(
        scope=AuditScope.GLOBAL,
        tenant_id=None,
        actor_type=AuditActorType.ANONYMOUS,
        actor_id=None,
        action=AuditAction.AUTH_LOGIN_FAILED,
        target_type=AuditTargetType.AUTHENTICATION,
        target_id=None,
    )
    asyncio.run(_append(auth_audit_uow_factory, event))

    direct_url = _rebuild_database_url(
        auth_test_database_url,
        database=make_url(auth_test_database_url).database or "postgres",
        sqlalchemy=False,
    )
    with psycopg.connect(direct_url) as connection:
        row = connection.execute(
            "SELECT scope, tenant_id, action FROM audit_events WHERE id = %s",
            (event.id,),
        ).fetchone()
    assert row is not None
    assert row[0] == "global"
    assert row[1] is None
    assert row[2] == "auth.login.failed"
