"""Unit tests for NOPQ AI budget reservation and reconciliation."""

from __future__ import annotations

import pytest
from closeros.application.ai_budget_service import AiBudgetError, AiBudgetService
from closeros.domain.ai_analysis import AiBudget, AiUsage


def _budget() -> AiBudget:
    return AiBudget(
        daily_input_token_budget=1_000,
        daily_output_token_budget=800,
        daily_cost_budget_microunits=50_000,
        reserved_input_tokens=100,
        reserved_output_tokens=120,
        reserved_cost_microunits=2_000,
        consumed_input_tokens=150,
        consumed_output_tokens=170,
        consumed_cost_microunits=5_000,
    )


def _usage(*, in_tokens: int = 40, out_tokens: int = 30, cost: int = 1_000) -> AiUsage:
    return AiUsage(
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        latency_milliseconds=1,
        estimated_cost_microunits=cost,
    )


def test_reserve_approves_when_remaining_budget_is_sufficient() -> None:
    service = AiBudgetService()
    reservation = service.reserve(
        current_budget=_budget(),
        requested_input_tokens=100,
        requested_output_tokens=80,
        requested_cost_microunits=3_000,
    )
    assert reservation.approved is True
    assert reservation.resulting_budget.reserved_input_tokens == 200
    assert reservation.resulting_budget.reserved_output_tokens == 200
    assert reservation.resulting_budget.reserved_cost_microunits == 5_000


def test_reserve_rejects_when_input_tokens_exceed_remaining() -> None:
    service = AiBudgetService()
    reservation = service.reserve(
        current_budget=_budget(),
        requested_input_tokens=10_000,
        requested_output_tokens=1,
        requested_cost_microunits=1,
    )
    assert reservation.approved is False
    assert reservation.resulting_budget == _budget()


@pytest.mark.parametrize(
    ("requested_out", "requested_cost"),
    [(2_000, 1), (1, 100_000)],
)
def test_reserve_rejects_on_output_or_cost_overflow(
    requested_out: int, requested_cost: int
) -> None:
    service = AiBudgetService()
    reservation = service.reserve(
        current_budget=_budget(),
        requested_input_tokens=1,
        requested_output_tokens=requested_out,
        requested_cost_microunits=requested_cost,
    )
    assert reservation.approved is False


def test_reserve_rejects_negative_requested_values() -> None:
    service = AiBudgetService()
    with pytest.raises(ValueError, match="non-negative"):
        service.reserve(
            current_budget=_budget(),
            requested_input_tokens=-1,
            requested_output_tokens=0,
            requested_cost_microunits=0,
        )


def test_reconcile_releases_reservation_and_adds_usage() -> None:
    service = AiBudgetService()
    budget = _budget()
    reconciled = service.reconcile(
        current_budget=budget,
        reserved_input_tokens=20,
        reserved_output_tokens=25,
        reserved_cost_microunits=500,
        actual_usage=_usage(in_tokens=19, out_tokens=21, cost=490),
    )
    assert reconciled.reserved_input_tokens == budget.reserved_input_tokens - 20
    assert reconciled.reserved_output_tokens == budget.reserved_output_tokens - 25
    assert reconciled.reserved_cost_microunits == budget.reserved_cost_microunits - 500
    assert reconciled.consumed_input_tokens == budget.consumed_input_tokens + 19
    assert reconciled.consumed_output_tokens == budget.consumed_output_tokens + 21
    assert reconciled.consumed_cost_microunits == budget.consumed_cost_microunits + 490


@pytest.mark.parametrize(
    ("reserved_in", "reserved_out", "reserved_cost"),
    [(999_999, 1, 1), (1, 999_999, 1), (1, 1, 999_999)],
)
def test_reconcile_rejects_when_reservation_exceeds_available(
    reserved_in: int,
    reserved_out: int,
    reserved_cost: int,
) -> None:
    service = AiBudgetService()
    with pytest.raises(AiBudgetError, match="exceed"):
        service.reconcile(
            current_budget=_budget(),
            reserved_input_tokens=reserved_in,
            reserved_output_tokens=reserved_out,
            reserved_cost_microunits=reserved_cost,
            actual_usage=_usage(),
        )
