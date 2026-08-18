"""Narrow action-candidate compilation and bounded discovery."""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, get_type_hints

from agent_surface.contracts import Action
from agent_surface.operations import OperationRegistry, UnknownOperationError
from agent_surface.references import MissingReferenceCodec, ReferenceRegistry, encode_scalar

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


class ActionPolicy(Protocol):
    def allows(self, candidate: ActionCandidate) -> bool: ...


@dataclass(frozen=True, slots=True)
class DenyAllActions:
    def allows(self, candidate: ActionCandidate) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class AllowActions:
    operations: frozenset[str]

    def allows(self, candidate: ActionCandidate) -> bool:
        return candidate.operation in self.operations


class ActionPublisher:
    """Bind and publish compiled candidates only through an explicit policy."""

    def __init__(
        self,
        *,
        references: ReferenceRegistry,
        policy: ActionPolicy,
    ) -> None:
        self._references = references
        self._policy = policy

    def publish(
        self,
        candidates: tuple[ActionCandidate, ...],
        *,
        values: dict[str, Any] | None = None,
    ) -> tuple[Action, ...]:
        explicit = values or {}
        return tuple(
            self._publish_one(candidate, explicit)
            for candidate in candidates
            if self._policy.allows(candidate)
        )

    def _publish_one(
        self,
        candidate: ActionCandidate,
        explicit: dict[str, Any],
    ) -> Action:
        safe_values = self._safe_values(candidate.context)
        argv = list(candidate.operation.split("."))
        bound: dict[str, Any] = {}
        slots: dict[str, Any] = {}
        unresolved = False

        for slot in candidate.slots:
            argv.append(f"--{slot.name.replace('_', '-')}")
            found, value = self._bound_value(slot, explicit, safe_values)
            if not found:
                unresolved = True
                argv.append(f"{{{slot.name}}}")
                descriptor: dict[str, Any] = {
                    "type": _annotation_name(slot.annotation),
                    "required": slot.required,
                }
                if slot.source is not None:
                    descriptor["source"] = slot.source
                slots[slot.name] = descriptor
                continue

            token, structured = self._encode_bound(value)
            argv.append(token)
            bound[slot.name] = structured

        command = None if unresolved else tuple(argv)
        command_template = tuple(argv) if unresolved else None
        return Action(
            rel=candidate.rel,
            description=candidate.description,
            command=command,
            command_template=command_template,
            operation=candidate.operation,
            bound=bound,
            slots=slots,
        )

    @staticmethod
    def _safe_values(context: object | None) -> dict[str, Any]:
        if context is None:
            return {}
        try:
            return dict(vars(context))
        except TypeError:
            return {}

    @staticmethod
    def _bound_value(
        slot: ActionSlotPlan,
        explicit: dict[str, Any],
        safe_values: dict[str, Any],
    ) -> tuple[bool, Any]:
        if slot.name in explicit and _compatible(slot.annotation, explicit[slot.name]):
            return True, explicit[slot.name]
        if slot.name in safe_values and _compatible(slot.annotation, safe_values[slot.name]):
            return True, safe_values[slot.name]
        if slot.default is not _MISSING:
            return True, slot.default
        return False, None

    def _encode_bound(self, value: object) -> tuple[str, Any]:
        try:
            return encode_scalar(value), value
        except MissingReferenceCodec:
            reference = self._references.encode(value)
            return reference.id, reference


def _compatible(annotation: Any, value: object) -> bool:
    if annotation is Any:
        return True
    if isinstance(annotation, type):
        if annotation in (bool, int, float, str):
            return type(value) is annotation
        return isinstance(value, annotation)
    return True


def _annotation_name(annotation: Any) -> str:
    return getattr(annotation, "__name__", str(annotation))


__all__ = [
    "ActionCandidate",
    "ActionCompiler",
    "ActionDefinitionError",
    "ActionPolicy",
    "ActionPublisher",
    "ActionSlotPlan",
    "AllowActions",
    "DenyAllActions",
    "action",
]
