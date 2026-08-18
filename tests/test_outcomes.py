from pydantic import BaseModel

from agent_surface import Action, ActionCollection, OperationError
from agent_surface.outcomes import NoActions, error_outcome, success_outcome


class Result(BaseModel):
    status: str


def test_success_outcome_keeps_result_and_bounded_actions() -> None:
    actions = ActionCollection(
        items=(Action(rel="inspect", command=("items", "inspect", "one")),),
        total=1,
        returned=1,
    )

    outcome = success_outcome(Result(status="ready"), next_actions=actions)

    assert outcome.ok is True
    assert outcome.result.status == "ready"
    assert outcome.next_actions == actions


def test_error_outcome_preserves_stable_domain_error_fields() -> None:
    error = OperationError(
        "resource_missing",
        "Resource was not found",
        details=({"loc": ("ref",), "type": "missing", "msg": "Not found"},),
        fix="Choose a listed reference.",
        retryable=True,
    )

    outcome = error_outcome(error)

    assert outcome.ok is False
    assert outcome.error.code == "resource_missing"
    assert outcome.error.details[0].path == ("ref",)
    assert outcome.error.details[0].code == "missing"
    assert outcome.fix == "Choose a listed reference."
    assert outcome.error.retryable is True


def test_no_actions_is_an_explicit_empty_provider() -> None:
    actions = NoActions().actions_for(operation="resource.inspect", result=Result(status="ready"))

    assert actions == ActionCollection()
