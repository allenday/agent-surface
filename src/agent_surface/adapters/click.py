"""Compile registered operations into an immutable Click projection plan."""

import inspect
import types
import typing
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

import click

from agent_surface.app import App
from agent_surface.operations import OperationDefinition, OperationRegistry
from agent_surface.references import ReferenceRegistry

CliParameterKind = Literal["argument", "option"]
CliValueKind = Literal["boolean", "float", "integer", "path", "reference", "string"]

_RESERVED_ROOTS = frozenset({"actions", "operations"})


class CliDefinitionError(Exception):
    """A registered model cannot be projected to an unambiguous CLI."""

    def __init__(self, code: str, message: str, *, fix: str) -> None:
        super().__init__(message)
        self.code = code
        self.fix = fix


@dataclass(frozen=True, slots=True)
class CliFieldPlan:
    name: str
    parameter_decls: tuple[str, ...]
    kind: CliParameterKind
    value_kind: CliValueKind
    annotation: Any
    required: bool
    multiple: bool = False
    choices: tuple[str, ...] = ()
    help: str = ""
    sensitive: bool = False
    reference_type: type[Any] | None = None


@dataclass(frozen=True, slots=True)
class CliCommandPlan:
    operation: str
    path: tuple[str, ...]
    summary: str
    fields: tuple[CliFieldPlan, ...]
    read_only: bool = False
    destructive: bool = False
    idempotent: bool = False
    open_world: bool = False


class CliPlanCompiler:
    """Compile deterministic Click plans without invoking handlers or model defaults."""

    def __init__(
        self,
        operations: OperationRegistry,
        *,
        references: ReferenceRegistry | None = None,
    ) -> None:
        self._operations = operations
        self._references = references or ReferenceRegistry()

    def compile(self) -> tuple[CliCommandPlan, ...]:
        definitions = self._operations.list()
        paths = {
            definition.name: self._operation_path(definition.name)
            for definition in definitions
        }
        self._validate_paths(paths)
        return tuple(
            self._compile_operation(definition, paths[definition.name])
            for definition in definitions
        )

    def _compile_operation(
        self,
        definition: OperationDefinition,
        path: tuple[str, ...],
    ) -> CliCommandPlan:
        fields = tuple(
            self._compile_field(name, field)
            for name, field in definition.input_model.model_fields.items()
        )
        self._validate_arguments(definition.name, fields)
        return CliCommandPlan(
            operation=definition.name,
            path=path,
            summary=definition.summary,
            fields=fields,
            read_only=definition.read_only,
            destructive=definition.destructive,
            idempotent=definition.idempotent,
            open_world=definition.open_world,
        )

    def _compile_field(self, name: str, field: Any) -> CliFieldPlan:
        annotation, optional = _unwrap_optional(field.annotation)
        item_annotation, multiple = _unwrap_collection(annotation)
        value_kind, choices, reference_type = self._value_shape(name, item_annotation)
        extra = field.json_schema_extra if isinstance(field.json_schema_extra, dict) else {}
        cli_extra = extra.get("cli", {}) if isinstance(extra.get("cli", {}), dict) else {}
        kind = cli_extra.get("kind", "option")
        if kind not in ("argument", "option"):
            raise self._unsupported(name, f"unknown CLI parameter kind {kind!r}")
        parameter_decls = (name,) if kind == "argument" else (f"--{name.replace('_', '-')}",)
        return CliFieldPlan(
            name=name,
            parameter_decls=parameter_decls,
            kind=kind,
            value_kind=value_kind,
            annotation=field.annotation,
            required=field.is_required() and not optional,
            multiple=multiple,
            choices=choices,
            help=field.description or "",
            sensitive=extra.get("sensitive") is True,
            reference_type=reference_type,
        )

    def _value_shape(
        self,
        name: str,
        annotation: Any,
    ) -> tuple[CliValueKind, tuple[str, ...], type[Any] | None]:
        if inspect.isclass(annotation) and self._references.supports_type(annotation):
            return "reference", (), annotation
        if annotation is str:
            return "string", (), None
        if annotation is bool:
            return "boolean", (), None
        if annotation is int:
            return "integer", (), None
        if annotation is float:
            return "float", (), None
        if annotation is Path:
            return "path", (), None
        origin = get_origin(annotation)
        if origin is Literal:
            values = get_args(annotation)
            if values and all(type(value) is str for value in values):
                return "string", tuple(values), None
        if inspect.isclass(annotation) and issubclass(annotation, Enum):
            values = tuple(member.value for member in annotation)
            if all(type(value) is str for value in values):
                return "string", values, None
        raise self._unsupported(name, f"unsupported annotation {annotation!r}")

    @staticmethod
    def _operation_path(name: str) -> tuple[str, ...]:
        path = tuple(name.split("."))
        if not path or any(not part for part in path):
            raise CliDefinitionError(
                "cli_command_conflict",
                f"Operation name cannot form a CLI path: {name}",
                fix="Use non-empty dot-separated command segments.",
            )
        if path[0] in _RESERVED_ROOTS:
            raise CliDefinitionError(
                "cli_command_conflict",
                f"Operation uses reserved generated namespace: {name}",
                fix="Rename the operation outside the operations and actions namespaces.",
            )
        return path

    @staticmethod
    def _validate_paths(paths: dict[str, tuple[str, ...]]) -> None:
        ordered = tuple(paths.items())
        for name, path in ordered:
            for other_name, other_path in ordered:
                is_prefix = len(path) < len(other_path) and other_path[: len(path)] == path
                if name != other_name and is_prefix:
                    raise CliDefinitionError(
                        "cli_command_conflict",
                        f"Operation is both a command and a command group: {name}",
                        fix=f"Rename {name} or {other_name} so neither path prefixes the other.",
                    )

    @staticmethod
    def _validate_arguments(operation: str, fields: tuple[CliFieldPlan, ...]) -> None:
        optional_seen = False
        for field in (item for item in fields if item.kind == "argument"):
            if not field.required:
                optional_seen = True
            elif optional_seen:
                raise CliDefinitionError(
                    "cli_command_conflict",
                    f"Required argument follows an optional argument in {operation}",
                    fix="Reorder fields or project the later field as an option.",
                )

    @staticmethod
    def _unsupported(name: str, reason: str) -> CliDefinitionError:
        return CliDefinitionError(
            "unsupported_cli_field",
            f"Cannot project field {name}: {reason}",
            fix="Use a supported scalar shape or register an explicit reference codec.",
        )


class ClickAdapter:
    """Build a mountable Click command tree from immutable operation plans."""

    def __init__(
        self,
        app: App,
        *,
        references: ReferenceRegistry | None = None,
    ) -> None:
        self._app = app
        self._references = references or ReferenceRegistry()
        self._plans = CliPlanCompiler(
            app.operations,
            references=self._references,
        ).compile()

    def command(self) -> click.Group:
        root = click.Group(
            name=self._app.name,
            help=f"{self._app.name} agent surface",
            context_settings={"help_option_names": ["-h", "--help"]},
        )
        for plan in self._plans:
            parent = root
            for segment in plan.path[:-1]:
                existing = parent.commands.get(segment)
                if existing is None:
                    group = click.Group(name=segment)
                    parent.add_command(group)
                    parent = group
                elif isinstance(existing, click.Group):
                    parent = existing
                else:  # pragma: no cover - compiler rejects this shape
                    raise AssertionError("compiled command path became ambiguous")
            parent.add_command(self._leaf_command(plan))
        return root

    @staticmethod
    def _leaf_command(plan: CliCommandPlan) -> click.Command:
        def callback(**params: Any) -> None:
            del params

        return click.Command(
            name=plan.path[-1],
            callback=callback,
            params=[_click_parameter(field) for field in plan.fields],
            help=plan.summary,
        )


def build_click_group(
    app: App,
    *,
    references: ReferenceRegistry | None = None,
) -> click.Group:
    return ClickAdapter(app, references=references).command()


def _click_parameter(field: CliFieldPlan) -> click.Parameter:
    parameter_type = _click_type(field)
    if field.kind == "argument":
        return click.Argument(
            field.parameter_decls,
            required=field.required,
            type=parameter_type,
        )
    declarations = field.parameter_decls
    if field.value_kind == "boolean":
        declarations = (f"{declarations[0]}/--no-{declarations[0][2:]}",)
    return click.Option(
        declarations,
        required=field.required,
        type=parameter_type,
        multiple=field.multiple,
        is_flag=field.value_kind == "boolean",
        default=None if not field.multiple else (),
        help=field.help,
        show_default=False,
    )


def _click_type(field: CliFieldPlan) -> click.ParamType[Any]:
    if field.choices:
        return click.Choice(field.choices, case_sensitive=True)
    return {
        "boolean": click.BOOL,
        "float": click.FLOAT,
        "integer": click.INT,
        "path": click.Path(path_type=str),
        "reference": click.STRING,
        "string": click.STRING,
    }[field.value_kind]


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    origin = get_origin(annotation)
    if origin in (types.UnionType, typing.Union):
        members = get_args(annotation)
        concrete = tuple(member for member in members if member is not type(None))
        if len(concrete) == 1 and len(concrete) != len(members):
            return concrete[0], True
    return annotation, False


def _unwrap_collection(annotation: Any) -> tuple[Any, bool]:
    origin = get_origin(annotation)
    if origin in (list, set, frozenset):
        arguments = get_args(annotation)
        if len(arguments) == 1:
            return arguments[0], True
    if origin is tuple:
        arguments = get_args(annotation)
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return arguments[0], True
    return annotation, False


__all__ = [
    "CliCommandPlan",
    "CliDefinitionError",
    "CliFieldPlan",
    "CliPlanCompiler",
    "ClickAdapter",
    "build_click_group",
]
