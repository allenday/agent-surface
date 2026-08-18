"""Narrow action-candidate compilation and bounded discovery."""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

from agent_surface.operations import OperationRegistry, UnknownOperationError

_ACTION_METADATA = "__agent_surface_action__"
_MISSING = object()


class ActionDefinitionError(Exception):
    def __init__(self, code: str, message: str, *, fix: str) -> None:
        super().__init__(message)
        self.code = code
        self.fix = fix


@dataclass(frozen=True, slots=True)
class ActionSlotPlan:
    name: str
    annotation: Any
    required: bool
    default: Any = _MISSING
    source: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ActionCandidate:
    operation: str
    rel: str
    description: str
    slots: tuple[ActionSlotPlan, ...]
    source: str
    context: object | None = None


@dataclass(frozen=True, slots=True)
class _ActionMetadata:
    operation: str
    rel: str | None
    description: str


def action(
    *,
    operation: str,
    rel: str | None = None,
    description: str = "",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark one method signature as an inert action candidate source."""

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        setattr(
            function,
            _ACTION_METADATA,
            _ActionMetadata(operation=operation, rel=rel, description=description),
        )
        return function

    return decorate


class ActionCompiler:
    """Compile immutable plans from registered models and explicitly decorated methods."""

    def __init__(self, operations: OperationRegistry) -> None:
        self._operations = operations

    def compile_operations(self) -> tuple[ActionCandidate, ...]:
        candidates = []
        for definition in self._operations.list():
            slots = tuple(
                ActionSlotPlan(
                    name=name,
                    annotation=field.annotation,
                    required=field.is_required(),
                    default=_MISSING if field.is_required() else field.default,
                )
                for name, field in definition.input_model.model_fields.items()
            )
            candidates.append(
                ActionCandidate(
                    operation=definition.name,
                    rel=definition.name,
                    description=definition.summary,
                    slots=slots,
                    source="operation",
                )
            )
        return tuple(candidates)

    def compile_object(self, instance: object) -> tuple[ActionCandidate, ...]:
        decorated: dict[str, tuple[Callable[..., Any], _ActionMetadata]] = {}
        for owner in reversed(type(instance).__mro__[:-1]):
            for name, value in owner.__dict__.items():
                metadata = getattr(value, _ACTION_METADATA, None)
                if metadata is not None and inspect.isfunction(value):
                    decorated[name] = (value, metadata)

        return tuple(
            self._compile_method(function, metadata, instance)
            for function, metadata in decorated.values()
        )

    def _compile_method(
        self,
        function: Callable[..., Any],
        metadata: _ActionMetadata,
        instance: object,
    ) -> ActionCandidate:
        try:
            definition = self._operations.describe(metadata.operation)
        except UnknownOperationError as error:
            raise ActionDefinitionError(
                "unknown_action_operation",
                f"Action targets unknown operation: {metadata.operation}",
                fix="Register the operation before compiling this action.",
            ) from error

        signature = inspect.signature(function)
        hints = get_type_hints(function)
        slots = []
        for index, parameter in enumerate(signature.parameters.values()):
            if index == 0 and parameter.name == "self":
                continue
            if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
                raise self._invalid_signature(function, "variadic parameters are not supported")
            annotation = hints.get(parameter.name, parameter.annotation)
            if annotation is inspect.Parameter.empty:
                raise self._invalid_signature(function, f"{parameter.name} is unannotated")
            required = parameter.default is inspect.Parameter.empty
            slots.append(
                ActionSlotPlan(
                    name=parameter.name,
                    annotation=annotation,
                    required=required,
                    default=_MISSING if required else parameter.default,
                )
            )
        return ActionCandidate(
            operation=metadata.operation,
            rel=metadata.rel or metadata.operation,
            description=metadata.description or definition.summary,
            slots=tuple(slots),
            source="method",
            context=instance,
        )

    @staticmethod
    def _invalid_signature(
        function: Callable[..., Any],
        reason: str,
    ) -> ActionDefinitionError:
        return ActionDefinitionError(
            "invalid_action_signature",
            f"Invalid action signature for {function.__qualname__}: {reason}",
            fix="Use named, annotated parameters without *args or **kwargs.",
        )


__all__ = [
    "ActionCandidate",
    "ActionCompiler",
    "ActionDefinitionError",
    "ActionSlotPlan",
    "action",
]
