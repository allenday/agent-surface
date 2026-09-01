"""Transport-neutral invocation outcome construction."""

import inspect
from typing import Any, Protocol

from pydantic import BaseModel

from agent_surface.budgets import OutputBudget
from agent_surface.contracts import (
    Action,
    ActionCollection,
    ErrorDetail,
    ErrorInfo,
    ErrorOutcome,
    SuccessOutcome,
)
from agent_surface.operations import OperationError


class ActionProvider(Protocol):
    """Return an already bounded relevant frontier for one invocation."""

    def actions_for(
        self,
        *,
        operation: str,
        request: BaseModel | None = None,
        result: object | None = None,
        error: OperationError | None = None,
    ) -> ActionCollection: ...

    def list_actions(
        self,
        *,
        cursor: str | None = None,
        budget: OutputBudget | None = None,
    ) -> ActionCollection: ...

    def explain(self, operation: str) -> Action | None: ...


class NoActions:
    """Explicit deny-by-default contextual action provider."""

    def actions_for(
        self,
        *,
        operation: str,
        request: BaseModel | None = None,
        result: object | None = None,
        error: OperationError | None = None,
    ) -> ActionCollection:
        return ActionCollection()

    def list_actions(
        self,
        *,
        cursor: str | None = None,
        budget: OutputBudget | None = None,
    ) -> ActionCollection:
        return ActionCollection()

    def explain(self, operation: str) -> Action | None:
        return None


def _provider_actions_for(
    provider: ActionProvider,
    *,
    operation: str,
    request: BaseModel | None = None,
    result: object | None = None,
    error: OperationError | None = None,
) -> ActionCollection:
    """Invoke providers with request context when their signature accepts it."""
    parameters = inspect.signature(provider.actions_for).parameters
    request_parameter = parameters.get("request")
    accepts_request = (
        request_parameter is not None
        and request_parameter.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    ) or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    arguments: dict[str, Any] = {
        "operation": operation,
        "result": result,
        "error": error,
    }
    if accepts_request:
        arguments["request"] = request
    return provider.actions_for(**arguments)


def success_outcome[ResultT](
    result: ResultT,
    *,
    next_actions: ActionCollection | None = None,
) -> SuccessOutcome[ResultT]:
    return SuccessOutcome(result=result, next_actions=next_actions or ActionCollection())


def error_outcome(
    error: OperationError,
    *,
    next_actions: ActionCollection | None = None,
) -> ErrorOutcome:
    return ErrorOutcome(
        error=ErrorInfo(
            code=error.code,
            message=error.message,
            details=tuple(_error_detail(item) for item in error.details),
            retryable=error.retryable,
        ),
        fix=error.fix,
        next_actions=next_actions or ActionCollection(),
    )


def _error_detail(item: dict[str, Any]) -> ErrorDetail:
    reserved = {"loc", "type", "code", "msg", "message", "input"}
    remainder = {key: value for key, value in item.items() if key not in reserved}
    value = item.get("input", remainder or None)
    return ErrorDetail(
        path=tuple(item.get("loc", ())),
        code=item.get("type", item.get("code")),
        message=item.get("msg", item.get("message")),
        value=value,
    )


__all__ = ["ActionProvider", "NoActions", "error_outcome", "success_outcome"]
