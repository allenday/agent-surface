import pytest
from pydantic import ValidationError

from agent_surface import Action
from agent_surface.budgets import (
    BoundedCollection,
    OutputBudget,
    OutputBudgetExceeded,
)


def continuation() -> Action:
    return Action(rel="next-page", command=("inventory", "list", "--cursor", "two"))


def test_output_budget_has_stable_positive_defaults_and_is_frozen() -> None:
    budget = OutputBudget()

    assert budget.max_items == 20
    assert budget.max_bytes == 65_536
    with pytest.raises(ValidationError, match="frozen"):
        budget.max_items = 10
    with pytest.raises(ValidationError):
        OutputBudget(max_items=0)
    with pytest.raises(ValidationError):
        OutputBudget(max_bytes=0)


def test_output_budget_exceeded_exposes_stable_structured_fields() -> None:
    error = OutputBudgetExceeded(
        code="response_too_large",
        message="Rendered response exceeds the byte budget",
        path=("result", "items"),
        details={"measured_bytes": 70_000, "max_bytes": 65_536},
        fix="Retry with a lower item limit.",
    )

    assert str(error) == "Rendered response exceeds the byte budget"
    assert error.code == "response_too_large"
    assert error.path == ("result", "items")
    assert error.details == {"measured_bytes": 70_000, "max_bytes": 65_536}
    assert error.fix == "Retry with a lower item limit."


def test_bounded_collection_validates_counts_and_continuation() -> None:
    with pytest.raises(ValidationError, match="returned"):
        BoundedCollection[str](items=("one",), total=1, returned=0)
    with pytest.raises(ValidationError, match="continuation"):
        BoundedCollection[str](items=("one",), total=2, returned=1, truncated=True)
    with pytest.raises(ValidationError, match="continuation"):
        BoundedCollection[str](
            items=("one",),
            total=1,
            returned=1,
            truncated=False,
            continuation=continuation(),
        )


def test_from_sequence_returns_complete_collection_within_budget() -> None:
    collection = BoundedCollection[str].from_sequence(
        ("one", "two"),
        budget=OutputBudget(max_items=2),
    )

    assert collection.items == ("one", "two")
    assert collection.total == 2
    assert collection.returned == 2
    assert collection.truncated is False
    assert collection.continuation is None


def test_from_sequence_requires_real_continuation_before_slicing() -> None:
    with pytest.raises(OutputBudgetExceeded) as raised:
        BoundedCollection[str].from_sequence(
            ("one", "two", "three"),
            budget=OutputBudget(max_items=2),
        )

    assert raised.value.code == "item_budget_exceeded"
    assert raised.value.details == {"total": 3, "max_items": 2}

    collection = BoundedCollection[str].from_sequence(
        ("one", "two", "three"),
        budget=OutputBudget(max_items=2),
        continuation=continuation(),
    )
    assert collection.items == ("one", "two")
    assert collection.total == 3
    assert collection.returned == 2
    assert collection.truncated is True
    assert collection.continuation == continuation()
    assert "..." not in collection.items
