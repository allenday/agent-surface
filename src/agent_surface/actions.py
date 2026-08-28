"""Narrow action-candidate compilation and bounded discovery."""

import base64
import binascii
import inspect
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, get_args, get_origin, get_type_hints

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from agent_surface.budgets import OutputBudget
from agent_surface.contracts import Action, ActionCollection
from agent_surface.operations import OperationRegistry, UnknownOperationError
from agent_surface.references import MissingReferenceCodec, ReferenceRegistry, encode_scalar

_ACTION_METADATA = "__agent_surface_action__"
_MISSING = object()


@dataclass(frozen=True, slots=True)
class _DefaultFactory:
    field: FieldInfo

    @property
    def needs_validated_data(self) -> bool:
        return self.field.default_factory_takes_validated_data is True

    def resolve(self, validated_data: dict[str, Any]) -> Any:
        return self.field.get_default(
            call_default_factory=True,
            validated_data=validated_data,
        )


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
    root: bool = False


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

    def __init__(
        self,
        operations: OperationRegistry,
        *,
        shared_input_model: type[BaseModel] | None = None,
    ) -> None:
        self._operations = operations
        self._shared_field_names = (
            frozenset(shared_input_model.model_fields)
            if shared_input_model is not None
            else frozenset()
        )

    def compile_operations(self) -> tuple[ActionCandidate, ...]:
        candidates = []
        for definition in self._operations.list():
            slots = tuple(
                ActionSlotPlan(
                    name=name,
                    annotation=field.annotation,
                    required=field.is_required(),
                    root=name in self._shared_field_names,
                    default=(
                        _MISSING
                        if field.is_required()
                        else (
                            _DefaultFactory(field)
                            if field.default_factory is not None
                            else field.default
                        )
                    ),
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
        seen: set[str] = set()
        for owner in type(instance).__mro__[:-1]:
            for name, value in owner.__dict__.items():
                if name in seen:
                    continue
                seen.add(name)
                if not inspect.isfunction(value):
                    continue
                metadata = value.__dict__.get(_ACTION_METADATA)
                if metadata is not None:
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
        argv: list[str] = []
        bound: dict[str, Any] = {}
        validated_data: dict[str, Any] = {}
        slots: dict[str, Any] = {}
        unresolved = False
        prior_slots_resolved = True

        for slot in (slot for slot in candidate.slots if slot.root):
            argv.append(f"--{slot.name.replace('_', '-')}")
            found, value = self._bound_value(
                slot, explicit, safe_values, validated_data, prior_slots_resolved
            )
            if not found:
                unresolved = True
                prior_slots_resolved = False
                argv.append(f"{{{slot.name}}}")
                slots[slot.name] = {
                    "type": _annotation_name(slot.annotation),
                    "required": slot.required,
                }
                continue
            validated_data[slot.name] = value
            token, structured = self._encode_bound(value)
            argv.append(token)
            bound[slot.name] = structured

        argv.extend(candidate.operation.split("."))
        for slot in (slot for slot in candidate.slots if not slot.root):
            argv.append(f"--{slot.name.replace('_', '-')}")
            found, value = self._bound_value(
                slot,
                explicit,
                safe_values,
                validated_data,
                prior_slots_resolved,
            )
            if not found:
                unresolved = True
                prior_slots_resolved = False
                argv.append(f"{{{slot.name}}}")
                descriptor: dict[str, Any] = {
                    "type": _annotation_name(slot.annotation),
                    "required": slot.required,
                }
                if slot.source is not None:
                    descriptor["source"] = slot.source
                slots[slot.name] = descriptor
                continue

            validated_data[slot.name] = value
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
        validated_data: dict[str, Any],
        prior_slots_resolved: bool,
    ) -> tuple[bool, Any]:
        if slot.name in explicit and _compatible(slot.annotation, explicit[slot.name]):
            return True, explicit[slot.name]
        if slot.name in safe_values and _compatible(slot.annotation, safe_values[slot.name]):
            return True, safe_values[slot.name]
        if isinstance(slot.default, _DefaultFactory):
            if slot.default.needs_validated_data and not prior_slots_resolved:
                return False, None
            return True, slot.default.resolve(validated_data)
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

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is typing.Annotated:
        return bool(arguments) and _compatible(arguments[0], value)
    if origin in (typing.Union, types.UnionType):
        return any(_compatible(member, value) for member in arguments)
    if origin is typing.Literal:
        return any(type(value) is type(member) and value == member for member in arguments)
    if origin is list:
        return (
            type(value) is list
            and len(arguments) == 1
            and all(_compatible(arguments[0], item) for item in value)
        )
    if origin is set:
        return (
            type(value) is set
            and len(arguments) == 1
            and all(_compatible(arguments[0], item) for item in value)
        )
    if origin is frozenset:
        return (
            type(value) is frozenset
            and len(arguments) == 1
            and all(_compatible(arguments[0], item) for item in value)
        )
    if origin is tuple:
        if type(value) is not tuple:
            return False
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return all(_compatible(arguments[0], item) for item in value)
        return len(arguments) == len(value) and all(
            _compatible(member, item) for member, item in zip(arguments, value, strict=True)
        )
    if origin is dict:
        return (
            type(value) is dict
            and len(arguments) == 2
            and all(
                _compatible(arguments[0], key) and _compatible(arguments[1], item)
                for key, item in value.items()
            )
        )
    if isinstance(annotation, type):
        if annotation in (bool, int, float, str):
            return type(value) is annotation
        return isinstance(value, annotation)
    return False


def _annotation_name(annotation: Any) -> str:
    return getattr(annotation, "__name__", str(annotation))


class InvalidActionCursor(Exception):
    code = "invalid_action_cursor"

    def __init__(self, cursor: str) -> None:
        super().__init__("Action cursor is invalid or out of range")
        self.cursor = cursor
        self.fix = "Restart discovery without a cursor."


class ActionCatalog:
    """Deterministic in-memory pages of already policy-filtered actions."""

    def __init__(
        self,
        actions: tuple[Action, ...],
        *,
        discovery_command: tuple[str, ...] = ("actions", "list"),
    ) -> None:
        self._actions = tuple(sorted(actions, key=_action_sort_key))
        self._discovery_command = discovery_command

    def page(
        self,
        *,
        cursor: str | None = None,
        budget: OutputBudget | None = None,
    ) -> ActionCollection:
        selected = budget or OutputBudget()
        offset = 0 if cursor is None else self._decode_cursor(cursor)
        if cursor is not None and offset >= len(self._actions):
            raise InvalidActionCursor(cursor)

        items = self._actions[offset : offset + selected.max_items]
        next_offset = offset + len(items)
        truncated = next_offset < len(self._actions)
        discover = None
        if truncated:
            discover = Action(
                rel="next-page",
                description="Return the next page of available actions",
                command=(
                    *self._discovery_command,
                    "--cursor",
                    self._encode_cursor(next_offset),
                    "--limit",
                    str(selected.max_items),
                ),
            )
        return ActionCollection(
            items=items,
            total=len(self._actions),
            returned=len(items),
            truncated=truncated,
            discover=discover,
        )

    @staticmethod
    def _encode_cursor(offset: int) -> str:
        encoded = base64.urlsafe_b64encode(f"v1:{offset}".encode()).decode()
        return encoded.rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> int:
        try:
            padding = "=" * (-len(cursor) % 4)
            decoded = base64.b64decode(
                cursor + padding,
                altchars=b"-_",
                validate=True,
            ).decode()
            version, raw_offset = decoded.split(":", 1)
            offset = int(raw_offset)
            if version != "v1" or offset < 0:
                raise ValueError
            return offset
        except (binascii.Error, UnicodeDecodeError, ValueError) as error:
            raise InvalidActionCursor(cursor) from error


def _action_sort_key(action_value: Action) -> tuple[str, str, tuple[str, ...]]:
    command = action_value.command or action_value.command_template or ()
    return action_value.operation or "", action_value.rel, command


__all__ = [
    "ActionCandidate",
    "ActionCatalog",
    "ActionCompiler",
    "ActionDefinitionError",
    "ActionPolicy",
    "ActionPublisher",
    "ActionSlotPlan",
    "AllowActions",
    "DenyAllActions",
    "InvalidActionCursor",
    "action",
]
