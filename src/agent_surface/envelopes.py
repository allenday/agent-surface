"""Application-owned canonical response-envelope extension point."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol, cast

from pydantic import BaseModel

from agent_surface.budgets import OutputBudget
from agent_surface.contracts import ActionCollection, CommandView
from agent_surface.operations import OperationDefinition, OperationError

_REDACTED = "<redacted>"


@dataclass(frozen=True, slots=True)
class Invocation:
    """Transport-neutral facts available when rendering one operation response."""

    operation: OperationDefinition
    request: Mapping[str, Any] | None
    result: BaseModel | None
    error: OperationError | None
    next_actions: ActionCollection
    budget: OutputBudget
    command: CommandView | None = None

    def bounded_error(self, error: OperationError) -> "Invocation":
        """Remove optional detail before retrying a renderer after a size failure."""
        return replace(
            self,
            request=None,
            result=None,
            error=error,
            next_actions=ActionCollection(),
            command=None,
        )


class CanonicalEnvelopeRenderer(Protocol):
    """Render an application's stable public response shape for one invocation."""

    output_model: type[BaseModel]

    def render(self, invocation: Invocation) -> BaseModel:
        """Return one validated, transport-neutral response document."""


def public_request(
    definition: OperationDefinition,
    request: BaseModel,
) -> dict[str, Any]:
    """Produce the safe request view available to public envelope renderers."""
    sensitive = {
        name
        for name, field in definition.input_model.model_fields.items()
        if isinstance(field.json_schema_extra, dict)
        and field.json_schema_extra.get("sensitive") is True
    }
    document = request.model_dump(mode="json")
    sensitive_values = tuple(document[name] for name in sensitive if name in document)

    def redact(value: Any, key: str | None = None) -> Any:
        if key in sensitive:
            return _REDACTED
        if any(type(value) is type(secret) and value == secret for secret in sensitive_values):
            return _REDACTED
        if isinstance(value, dict):
            return {str(item_key): redact(item, str(item_key)) for item_key, item in value.items()}
        if isinstance(value, tuple):
            return tuple(redact(item) for item in value)
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    return cast(dict[str, Any], redact(document))


__all__ = ["CanonicalEnvelopeRenderer", "Invocation", "public_request"]
