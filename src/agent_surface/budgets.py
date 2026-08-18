"""Explicit output budgets and bounded collection contracts."""

from collections.abc import Sequence
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from agent_surface.contracts import Action, ContractModel

BudgetErrorCode = Literal["item_budget_exceeded", "response_too_large"]


class OutputBudget(ContractModel):
    """Stable item and encoded-byte limits for one rendered document."""

    max_items: int = Field(default=20, ge=1)
    max_bytes: int = Field(default=65_536, ge=1)


class OutputBudgetExceeded(Exception):
    """A complete value cannot be represented within its output budget."""

    def __init__(
        self,
        *,
        code: BudgetErrorCode,
        message: str,
        path: tuple[str | int, ...] = (),
        details: dict[str, Any] | None = None,
        fix: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.details = details or {}
        self.fix = fix


class BoundedCollection[ItemT](ContractModel):
    """A collection that makes any truncation and continuation explicit."""

    items: tuple[ItemT, ...] = ()
    total: int = Field(default=0, ge=0)
    returned: int = Field(default=0, ge=0)
    truncated: bool = False
    continuation: Action | None = None

    @model_validator(mode="after")
    def validate_collection(self) -> Self:
        if self.returned != len(self.items):
            raise ValueError("returned must equal the number of items")
        if self.total < self.returned:
            raise ValueError("total must be greater than or equal to returned")
        if self.truncated != (self.total > self.returned):
            raise ValueError("truncated must indicate omitted items")
        if self.truncated != (self.continuation is not None):
            raise ValueError("continuation is required exactly when truncated")
        return self

    @classmethod
    def from_sequence(
        cls,
        items: Sequence[ItemT],
        *,
        budget: OutputBudget | None = None,
        continuation: Action | None = None,
    ) -> Self:
        budget = budget or OutputBudget()
        total = len(items)
        if total <= budget.max_items:
            return cls(items=tuple(items), total=total, returned=total)
        if continuation is None:
            raise OutputBudgetExceeded(
                code="item_budget_exceeded",
                message="Collection exceeds the item budget",
                details={"total": total, "max_items": budget.max_items},
                fix="Provide a continuation action or use a lower input limit.",
            )
        bounded = tuple(items[: budget.max_items])
        return cls(
            items=bounded,
            total=total,
            returned=len(bounded),
            truncated=True,
            continuation=continuation,
        )


__all__ = ["BoundedCollection", "OutputBudget", "OutputBudgetExceeded"]
