"""Daily AI budget reservation and reconciliation in integer microunits."""

from __future__ import annotations

from dataclasses import dataclass

from closeros.domain.ai_analysis import AiBudget, AiUsage


class AiBudgetError(Exception):
    """Raised when AI budget operations are invalid."""


def _validate_non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    approved: bool
    requested_input_tokens: int
    requested_output_tokens: int
    requested_cost_microunits: int
    resulting_budget: AiBudget

    def __post_init__(self) -> None:
        if type(self.approved) is not bool:
            raise TypeError("approved must be a bool")
        for field_name in (
            "requested_input_tokens",
            "requested_output_tokens",
            "requested_cost_microunits",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_non_negative_int(getattr(self, field_name), field_name),
            )
        if not isinstance(self.resulting_budget, AiBudget):
            raise TypeError("resulting_budget must be an AiBudget")


class AiBudgetService:
    def reserve(
        self,
        *,
        current_budget: AiBudget,
        requested_input_tokens: int,
        requested_output_tokens: int,
        requested_cost_microunits: int,
    ) -> BudgetReservation:
        if not isinstance(current_budget, AiBudget):
            raise TypeError("current_budget must be an AiBudget")
        requested_in = _validate_non_negative_int(requested_input_tokens, "requested_input_tokens")
        requested_out = _validate_non_negative_int(
            requested_output_tokens, "requested_output_tokens"
        )
        requested_cost = _validate_non_negative_int(
            requested_cost_microunits,
            "requested_cost_microunits",
        )

        remaining_input = current_budget.daily_input_token_budget - (
            current_budget.reserved_input_tokens + current_budget.consumed_input_tokens
        )
        remaining_output = current_budget.daily_output_token_budget - (
            current_budget.reserved_output_tokens + current_budget.consumed_output_tokens
        )
        remaining_cost = current_budget.daily_cost_budget_microunits - (
            current_budget.reserved_cost_microunits + current_budget.consumed_cost_microunits
        )
        approved = (
            requested_in <= remaining_input
            and requested_out <= remaining_output
            and requested_cost <= remaining_cost
        )
        if not approved:
            return BudgetReservation(
                approved=False,
                requested_input_tokens=requested_in,
                requested_output_tokens=requested_out,
                requested_cost_microunits=requested_cost,
                resulting_budget=current_budget,
            )
        next_budget = AiBudget(
            daily_input_token_budget=current_budget.daily_input_token_budget,
            daily_output_token_budget=current_budget.daily_output_token_budget,
            daily_cost_budget_microunits=current_budget.daily_cost_budget_microunits,
            reserved_input_tokens=current_budget.reserved_input_tokens + requested_in,
            reserved_output_tokens=current_budget.reserved_output_tokens + requested_out,
            reserved_cost_microunits=current_budget.reserved_cost_microunits + requested_cost,
            consumed_input_tokens=current_budget.consumed_input_tokens,
            consumed_output_tokens=current_budget.consumed_output_tokens,
            consumed_cost_microunits=current_budget.consumed_cost_microunits,
        )
        return BudgetReservation(
            approved=True,
            requested_input_tokens=requested_in,
            requested_output_tokens=requested_out,
            requested_cost_microunits=requested_cost,
            resulting_budget=next_budget,
        )

    def reconcile(
        self,
        *,
        current_budget: AiBudget,
        reserved_input_tokens: int,
        reserved_output_tokens: int,
        reserved_cost_microunits: int,
        actual_usage: AiUsage,
    ) -> AiBudget:
        if not isinstance(current_budget, AiBudget):
            raise TypeError("current_budget must be an AiBudget")
        if not isinstance(actual_usage, AiUsage):
            raise TypeError("actual_usage must be an AiUsage")
        reserved_in = _validate_non_negative_int(reserved_input_tokens, "reserved_input_tokens")
        reserved_out = _validate_non_negative_int(reserved_output_tokens, "reserved_output_tokens")
        reserved_cost = _validate_non_negative_int(
            reserved_cost_microunits,
            "reserved_cost_microunits",
        )
        if reserved_in > current_budget.reserved_input_tokens:
            raise AiBudgetError("reserved input tokens exceed available reservation")
        if reserved_out > current_budget.reserved_output_tokens:
            raise AiBudgetError("reserved output tokens exceed available reservation")
        if reserved_cost > current_budget.reserved_cost_microunits:
            raise AiBudgetError("reserved cost exceeds available reservation")
        return AiBudget(
            daily_input_token_budget=current_budget.daily_input_token_budget,
            daily_output_token_budget=current_budget.daily_output_token_budget,
            daily_cost_budget_microunits=current_budget.daily_cost_budget_microunits,
            reserved_input_tokens=current_budget.reserved_input_tokens - reserved_in,
            reserved_output_tokens=current_budget.reserved_output_tokens - reserved_out,
            reserved_cost_microunits=current_budget.reserved_cost_microunits - reserved_cost,
            consumed_input_tokens=current_budget.consumed_input_tokens + actual_usage.input_tokens,
            consumed_output_tokens=current_budget.consumed_output_tokens
            + actual_usage.output_tokens,
            consumed_cost_microunits=(
                current_budget.consumed_cost_microunits + actual_usage.estimated_cost_microunits
            ),
        )
