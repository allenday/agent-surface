"""Compile registered operations into an immutable Click projection plan."""

import asyncio
import inspect
import math
import sys
import types
import typing
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Literal, cast, get_args, get_origin

import click
from click.core import ParameterSource
from pydantic import BaseModel

from agent_surface.actions import InvalidActionCursor
from agent_surface.app import App
from agent_surface.budgets import OutputBudget, OutputBudgetExceeded
from agent_surface.composition import ComposedApp
from agent_surface.contracts import CommandView, ErrorEnvelope, ParsedCommand, SuccessEnvelope
from agent_surface.discovery import OperationCatalog
from agent_surface.envelopes import CanonicalEnvelopeRenderer, Invocation, public_request
from agent_surface.operations import (
    OperationDefinition,
    OperationError,
    OperationInputError,
    OperationOutputError,
    OperationRegistry,
)
from agent_surface.outcomes import ActionProvider, NoActions, _provider_actions_for, error_outcome
from agent_surface.references import ReferenceError, ReferenceRegistry, encode_scalar
from agent_surface.rendering import RenderOptions, render, render_envelope

CliParameterKind = Literal["argument", "option"]
CliValueKind = Literal["boolean", "float", "integer", "path", "reference", "string"]
CliFieldSource = Literal["argv", "stdin"]

_RESERVED_ROOTS = frozenset({"actions", "operations"})
_RESERVED_FIELDS = frozenset({"format", "yaml_style"})
_RESERVED_OPTIONS = frozenset({"--format", "--yaml-style"})
_RAW_ARGV_KEY = "agent_surface.raw_argv"
_REDACTED = "<redacted>"
_MIN_CLI_BYTES = 1_024
_DEFAULT_STDIN_MAX_BYTES = 8_192


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
    minimum: int | None = None
    maximum: int | None = None
    help: str = ""
    sensitive: bool = False
    reference_type: type[Any] | None = None
    source: CliFieldSource = "argv"
    stdin_flag: str | None = None
    stdin_max_bytes: int | None = None
    strip_trailing_newline: bool = True


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
        shared_input_model: type[BaseModel] | None = None,
    ) -> None:
        self._operations = operations
        self._references = references or ReferenceRegistry()
        self._shared_input_model = shared_input_model
        self.shared_fields: tuple[CliFieldPlan, ...] = ()

    def compile(self) -> tuple[CliCommandPlan, ...]:
        if self._shared_input_model is not None:
            self.shared_fields = tuple(
                self._compile_field(name, field)
                for name, field in self._shared_input_model.model_fields.items()
            )
            for field in self.shared_fields:
                if field.kind != "option" or field.source != "argv":
                    raise CliDefinitionError(
                        "cli_parameter_conflict",
                        f"Shared input {field.name} must be an argv option",
                        fix="Use the default option projection for every shared input field.",
                    )
        definitions = self._operations.list()
        paths = {
            definition.name: self._operation_path(definition.name) for definition in definitions
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
        shared_names = (
            set(self._shared_input_model.model_fields)
            if self._shared_input_model is not None
            else set()
        )
        fields = tuple(
            self._compile_field(name, field)
            for name, field in definition.input_model.model_fields.items()
            if name not in shared_names
        )
        self._validate_arguments(definition.name, fields)
        self._validate_transport_fields(definition, (*self.shared_fields, *fields))
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
        annotation, _ = _unwrap_optional(field.annotation)
        item_annotation, multiple = _unwrap_collection(annotation)
        value_kind, choices, reference_type = self._value_shape(name, item_annotation)
        minimum, maximum = _integer_bounds(field) if value_kind == "integer" else (None, None)
        extra = field.json_schema_extra if isinstance(field.json_schema_extra, dict) else {}
        cli_extra = extra.get("cli", {}) if isinstance(extra.get("cli", {}), dict) else {}
        kind = cli_extra.get("kind", "option")
        if kind not in ("argument", "option"):
            raise self._unsupported(name, f"unknown CLI parameter kind {kind!r}")
        source = cli_extra.get("source", "argv")
        if source not in ("argv", "stdin"):
            raise self._unsupported(name, f"unknown CLI field source {source!r}")
        sensitive = extra.get("sensitive") is True
        stdin_max_bytes: int | None = None
        strip_trailing_newline = True
        if source == "stdin":
            if not sensitive:
                raise CliDefinitionError(
                    "cli_parameter_conflict",
                    f"stdin field {name} must be sensitive",
                    fix="Mark the field sensitive or project it from argv.",
                )
            if kind != "option" or multiple or value_kind != "string":
                raise CliDefinitionError(
                    "cli_parameter_conflict",
                    f"stdin field {name} must be a singular string option",
                    fix="Use a sensitive str field without cli.kind or a collection annotation.",
                )
            candidate_max_bytes = cli_extra.get("max_bytes", _DEFAULT_STDIN_MAX_BYTES)
            if type(candidate_max_bytes) is not int or candidate_max_bytes < 1:
                raise CliDefinitionError(
                    "cli_parameter_conflict",
                    f"stdin field {name} max_bytes must be a positive integer",
                    fix="Set cli.max_bytes to a positive integer.",
                )
            candidate_strip = cli_extra.get("strip_trailing_newline", True)
            if type(candidate_strip) is not bool:
                raise CliDefinitionError(
                    "cli_parameter_conflict",
                    f"stdin field {name} strip_trailing_newline must be boolean",
                    fix="Set cli.strip_trailing_newline to true or false.",
                )
            stdin_max_bytes = candidate_max_bytes
            strip_trailing_newline = candidate_strip
        parameter_decls = self._parameter_decls(
            name,
            cli_extra,
            kind=kind,
            source=source,
        )
        return CliFieldPlan(
            name=name,
            parameter_decls=parameter_decls,
            kind=kind,
            value_kind=value_kind,
            annotation=field.annotation,
            required=field.is_required(),
            multiple=multiple,
            choices=choices,
            minimum=minimum,
            maximum=maximum,
            help=field.description or "",
            sensitive=sensitive,
            reference_type=reference_type,
            source=source,
            stdin_flag=f"--{name.replace('_', '-')}-stdin" if source == "stdin" else None,
            stdin_max_bytes=stdin_max_bytes,
            strip_trailing_newline=strip_trailing_newline,
        )

    @staticmethod
    def _parameter_decls(
        name: str,
        cli_extra: dict[str, Any],
        *,
        kind: CliParameterKind,
        source: CliFieldSource,
    ) -> tuple[str, ...]:
        options = cli_extra.get("options")
        if options is None:
            return (
                ()
                if source == "stdin"
                else (name,)
                if kind == "argument"
                else (f"--{name.replace('_', '-')}",)
            )
        if kind != "option" or source != "argv":
            raise CliDefinitionError(
                "cli_parameter_conflict",
                f"CLI options metadata for {name} requires an argv option field",
                fix="Use cli.options only with the default argv option projection.",
            )
        if (
            not isinstance(options, list)
            or not options
            or any(
                type(option) is not str
                or not option.startswith("--")
                or len(option) == 2
                or option.startswith("---")
                or any(character.isspace() for character in option)
                or "/" in option
                or "=" in option
                for option in options
            )
            or len(set(options)) != len(options)
        ):
            raise CliDefinitionError(
                "cli_parameter_conflict",
                f"CLI options metadata for {name} must be unique long options",
                fix=('Set cli.options to a non-empty list such as ["--apply", "--apply-changes"].'),
            )
        return tuple(options)

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
    def _validate_transport_fields(
        definition: OperationDefinition,
        fields: tuple[CliFieldPlan, ...],
    ) -> None:
        stdin_fields = tuple(field for field in fields if field.source == "stdin")
        if len(stdin_fields) > 1:
            raise CliDefinitionError(
                "cli_parameter_conflict",
                f"Operation {definition.name} declares multiple stdin fields",
                fix="Project at most one field from stdin for a CLI invocation.",
            )
        stdin_flags = {
            field.stdin_flag: field for field in stdin_fields if field.stdin_flag is not None
        }
        option_fields: dict[str, CliFieldPlan] = {}
        for field in fields:
            if field.source == "argv" and field.kind == "option":
                for option in _option_declarations(field):
                    if option in _RESERVED_OPTIONS:
                        raise CliDefinitionError(
                            "cli_parameter_conflict",
                            (
                                f"Option {option} for {field.name} conflicts with "
                                "generated rendering options"
                            ),
                            fix="Choose a different cli.options value.",
                        )
                    other = option_fields.get(option)
                    if other is not None:
                        raise CliDefinitionError(
                            "cli_parameter_conflict",
                            f"Option {option} is declared by both {other.name} and {field.name}",
                            fix="Give each argv option a unique cli.options value.",
                        )
                    option_fields[option] = field
            if (
                field.source == "argv"
                and field.kind == "option"
                and field.parameter_decls[0] in stdin_flags
            ):
                stdin_field = stdin_flags[field.parameter_decls[0]]
                raise CliDefinitionError(
                    "cli_parameter_conflict",
                    (
                        f"Option {field.parameter_decls[0]} for {field.name} conflicts with "
                        f"the generated stdin flag for {stdin_field.name}"
                    ),
                    fix="Rename one field or project the other field from a different source.",
                )
            if field.name in _RESERVED_FIELDS:
                raise CliDefinitionError(
                    "cli_parameter_conflict",
                    f"Field conflicts with a generated rendering option: {field.name}",
                    fix=f"Rename {field.name}; --format and --yaml-style belong to the adapter.",
                )
            if field.kind == "argument" and field.multiple:
                raise CliDefinitionError(
                    "unsupported_cli_field",
                    f"Cannot project repeated positional field {field.name} losslessly",
                    fix="Project the repeated field as an option.",
                )
            if definition.destructive and field.name == "confirm" and field.value_kind != "boolean":
                raise CliDefinitionError(
                    "cli_parameter_conflict",
                    "Destructive operation field confirm must be boolean",
                    fix=(
                        "Declare confirm as bool or remove it and use the generated --confirm flag."
                    ),
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
        action_provider: ActionProvider | None = None,
        render_options: RenderOptions | None = None,
        argv_provider: Callable[[], Sequence[str]] | None = None,
        envelope_renderer: CanonicalEnvelopeRenderer | None = None,
        operation_error_exit_code: Callable[[str], int] | None = None,
    ) -> None:
        self._app = app
        self._references = references or ReferenceRegistry()
        self._action_provider = action_provider or NoActions()
        self._render_options = render_options or RenderOptions()
        if self._render_options.budget.max_bytes < _MIN_CLI_BYTES:
            raise CliDefinitionError(
                "cli_budget_too_small",
                f"Click output budget must be at least {_MIN_CLI_BYTES} bytes",
                fix="Raise max_bytes so a structured error envelope can always be emitted.",
            )
        self._argv_provider = argv_provider
        self._envelope_renderer = envelope_renderer
        compiler = CliPlanCompiler(
            app.operations,
            references=self._references,
            shared_input_model=app.shared_input_model,
        )
        self._plans = compiler.compile()
        self._shared_fields = compiler.shared_fields
        self._operation_error_exit_code = operation_error_exit_code or (lambda _code: 4)

    def command(self) -> click.Group:
        root = _SurfaceGroup(
            name=self._app.name,
            help=f"{self._app.name} agent surface",
            context_settings={"help_option_names": ["-h", "--help"]},
            adapter=self,
            path=(),
            params=[_click_parameter(field) for field in self._shared_fields],
        )
        for plan in self._plans:
            parent: click.Group = root
            for index, segment in enumerate(plan.path[:-1]):
                existing = parent.commands.get(segment)
                if existing is None:
                    group = _SurfaceGroup(
                        name=segment,
                        adapter=self,
                        path=plan.path[: index + 1],
                    )
                    parent.add_command(group)
                    parent = group
                elif isinstance(existing, click.Group):
                    parent = existing
                else:  # pragma: no cover - compiler rejects this shape
                    raise AssertionError("compiled command path became ambiguous")
            parent.add_command(self._leaf_command(plan))
        self._add_discovery(root)
        return root

    def _capture_raw(self, info_name: str | None, args: list[str]) -> tuple[str, ...]:
        if self._argv_provider is not None:
            return tuple(self._argv_provider())
        return (info_name or self._app.name, *tuple(args))

    def _add_discovery(self, root: click.Group) -> None:
        operations = _SurfaceGroup(
            "operations",
            help="Discover registered operations.",
            adapter=self,
            path=("operations",),
        )
        actions = _SurfaceGroup(
            "actions",
            help="Discover policy-approved actions.",
            adapter=self,
            path=("actions",),
        )
        catalog = OperationCatalog(
            self._app.operations,
            discovery_command=(self._app.name, "operations", "list"),
        )

        @click.pass_context
        def list_operations(
            context: click.Context,
            /,
            cursor: str | None,
            limit: int,
            _surface_format: str,
            _surface_yaml_style: str,
        ) -> None:
            command = self._discovery_view(
                context,
                ("operations", "list"),
                options={"cursor": cursor, "limit": limit},
            )
            try:
                page = catalog.page(
                    cursor=cursor,
                    budget=OutputBudget(
                        max_items=limit,
                        max_bytes=self._render_options.budget.max_bytes,
                    ),
                )
                self._emit_success(
                    command,
                    page,
                    document_format=_surface_format,
                    yaml_style=_surface_yaml_style,
                )
            except OperationError as error:
                self._emit_error(
                    command,
                    error,
                    exit_code=2,
                    operation="operations.list",
                    document_format=_surface_format,
                    yaml_style=_surface_yaml_style,
                )

        @click.pass_context
        def describe_operation(
            context: click.Context,
            /,
            name: str,
            _surface_format: str,
            _surface_yaml_style: str,
        ) -> None:
            command = self._discovery_view(
                context,
                ("operations", "describe"),
                arguments={"name": name},
            )
            try:
                self._emit_success(
                    command,
                    catalog.describe(name),
                    document_format=_surface_format,
                    yaml_style=_surface_yaml_style,
                )
            except OperationError as error:
                self._emit_error(
                    command,
                    error,
                    exit_code=2,
                    operation="operations.describe",
                    document_format=_surface_format,
                    yaml_style=_surface_yaml_style,
                )

        @click.pass_context
        def list_actions(
            context: click.Context,
            /,
            cursor: str | None,
            limit: int,
            _surface_format: str,
            _surface_yaml_style: str,
        ) -> None:
            command = self._discovery_view(
                context,
                ("actions", "list"),
                options={"cursor": cursor, "limit": limit},
            )
            try:
                page = self._action_provider.list_actions(
                    cursor=cursor,
                    budget=OutputBudget(
                        max_items=limit,
                        max_bytes=self._render_options.budget.max_bytes,
                    ),
                )
                self._emit_success(
                    command,
                    page,
                    document_format=_surface_format,
                    yaml_style=_surface_yaml_style,
                )
            except InvalidActionCursor as error:
                operation_error = OperationError(
                    error.code,
                    str(error),
                    fix=error.fix,
                )
                self._emit_error(
                    command,
                    operation_error,
                    exit_code=2,
                    operation="actions.list",
                    document_format=_surface_format,
                    yaml_style=_surface_yaml_style,
                )
            except Exception:
                self._emit_error(
                    command,
                    OperationError(
                        "internal_error",
                        "Action discovery failed unexpectedly",
                        fix="Retry or inspect application diagnostics.",
                    ),
                    exit_code=70,
                    operation="actions.list",
                    document_format=_surface_format,
                    yaml_style=_surface_yaml_style,
                )

        @click.pass_context
        def explain_action(
            context: click.Context,
            /,
            operation: str,
            _surface_format: str,
            _surface_yaml_style: str,
        ) -> None:
            command = self._discovery_view(
                context,
                ("actions", "explain"),
                arguments={"operation": operation},
            )
            try:
                action = self._action_provider.explain(operation)
            except Exception:
                self._emit_error(
                    command,
                    OperationError(
                        "internal_error",
                        "Action discovery failed unexpectedly",
                        fix="Retry or inspect application diagnostics.",
                    ),
                    exit_code=70,
                    operation="actions.explain",
                    document_format=_surface_format,
                    yaml_style=_surface_yaml_style,
                )
            if action is None:
                self._emit_error(
                    command,
                    OperationError(
                        "action_not_found",
                        f"No published action is available for {operation}",
                        fix="Run actions list to discover policy-approved actions.",
                    ),
                    exit_code=2,
                    operation="actions.explain",
                    document_format=_surface_format,
                    yaml_style=_surface_yaml_style,
                )
            self._emit_success(
                command,
                action,
                document_format=_surface_format,
                yaml_style=_surface_yaml_style,
            )

        operations.add_command(
            _SurfaceDiscoveryCommand(
                "list",
                callback=list_operations,
                params=[*_pagination_parameters(), *_render_parameters()],
                help="List a bounded page of registered operations.",
                adapter=self,
                path=("operations", "list"),
            )
        )
        operations.add_command(
            _SurfaceDiscoveryCommand(
                "describe",
                callback=describe_operation,
                params=[click.Argument(("name",), required=True), *_render_parameters()],
                help="Describe one operation and its Pydantic schemas.",
                adapter=self,
                path=("operations", "describe"),
            )
        )
        actions.add_command(
            _SurfaceDiscoveryCommand(
                "list",
                callback=list_actions,
                params=[*_pagination_parameters(), *_render_parameters()],
                help="List a bounded page of policy-approved actions.",
                adapter=self,
                path=("actions", "list"),
            )
        )
        actions.add_command(
            _SurfaceDiscoveryCommand(
                "explain",
                callback=explain_action,
                params=[click.Argument(("operation",), required=True), *_render_parameters()],
                help="Explain one policy-approved action.",
                adapter=self,
                path=("actions", "explain"),
            )
        )
        root.add_command(operations)
        root.add_command(actions)

    def _emit_success(
        self,
        command: CommandView,
        result: object,
        *,
        document_format: str,
        yaml_style: str,
    ) -> None:
        envelope = SuccessEnvelope(command=command, result=result)
        try:
            rendered = render(
                envelope,
                options=self._selected_render_options(document_format, yaml_style),
            )
        except OutputBudgetExceeded as error:
            self._emit_error(
                _compact_command(command),
                OperationError(error.code, str(error), details=(error.details,), fix=error.fix),
                exit_code=70,
                document_format=document_format,
                yaml_style=yaml_style,
            )
        click.echo(rendered, nl=False)

    def _discovery_view(
        self,
        context: click.Context,
        path: tuple[str, ...],
        *,
        arguments: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> CommandView:
        raw = tuple(context.meta.get(_RAW_ARGV_KEY, (self._app.name, *path)))
        return CommandView(
            raw=raw,
            parsed=ParsedCommand(
                path=path,
                args=arguments or {},
                options={key: value for key, value in (options or {}).items() if value is not None},
            ),
        )

    def _leaf_command(self, plan: CliCommandPlan) -> click.Command:
        @click.pass_context
        def callback(context: click.Context, /, **params: Any) -> None:
            self._invoke(context, command._plan, params)

        parameters = [
            _click_parameter(
                field,
                required_override=False if plan.destructive and field.name == "confirm" else None,
            )
            for field in plan.fields
            if field.source == "argv"
        ]
        parameters.extend(_stdin_parameters(plan.fields))
        if plan.destructive and not any(field.name == "confirm" for field in plan.fields):
            parameters.append(
                click.Option(
                    ("--confirm", "_surface_confirm"),
                    is_flag=True,
                    default=False,
                    help="Confirm this destructive operation.",
                )
            )
        parameters.extend(_render_parameters())

        command = _SurfaceCommand(
            name=plan.path[-1],
            callback=callback,
            params=parameters,
            help=plan.summary,
            adapter=self,
            plan=plan,
        )
        return command

    def _invoke(
        self,
        context: click.Context,
        plan: CliCommandPlan,
        params: dict[str, Any],
    ) -> None:
        document_format = params.pop("_surface_format")
        yaml_style = params.pop("_surface_yaml_style")
        transport_confirm = params.pop("_surface_confirm", False)
        command = self._command_view(
            context,
            plan,
            params,
            transport_confirm=transport_confirm,
        )
        document_format, yaml_style = _render_choices_from_raw(command.raw)
        definition = self._app.operations.describe(plan.operation)
        public_operation = ".".join(plan.path)
        public_definition = replace(definition, name=public_operation)
        request: BaseModel | None = None
        missing_shared = tuple(
            field
            for field in self._shared_fields
            if field.required
            and self._surface_context(context).get_parameter_source(field.name)
            is not ParameterSource.COMMANDLINE
        )
        if missing_shared:
            option = missing_shared[0].parameter_decls[0]
            self._emit_error(
                command,
                OperationError(
                    "usage_error",
                    f"Missing option {option!r}.",
                    fix=f"Provide {option} and retry.",
                ),
                exit_code=2,
                operation=public_operation,
                document_format=document_format,
                yaml_style=yaml_style,
                definition=public_definition,
            )
        try:
            payload = self._payload(context, plan, params)
        except OperationError as error:
            self._emit_error(
                command,
                error,
                exit_code=2,
                operation=public_operation,
                document_format=document_format,
                yaml_style=yaml_style,
                definition=public_definition,
                request=request,
                sensitive_values=self._sensitive_param_values(context, plan, params),
            )
        except ReferenceError as error:
            self._emit_error(
                command,
                OperationError(error.code, str(error), fix=error.fix),
                exit_code=2,
                operation=public_operation,
                document_format=document_format,
                yaml_style=yaml_style,
                definition=public_definition,
                request=request,
                sensitive_values=self._sensitive_param_values(context, plan, params),
            )
        except Exception:
            self._emit_error(
                command,
                OperationError(
                    "invalid_reference",
                    "Reference token could not be decoded",
                    fix="Use a reference returned by discovery.",
                ),
                exit_code=2,
                operation=public_operation,
                document_format=document_format,
                yaml_style=yaml_style,
                definition=public_definition,
                request=request,
                sensitive_values=self._sensitive_param_values(context, plan, params),
            )

        confirmed = transport_confirm or payload.get("confirm") is True
        if plan.destructive and not confirmed:
            self._emit_error(
                command,
                OperationError(
                    "confirmation_required",
                    "Destructive operation requires explicit confirmation",
                    fix="Retry with --confirm after reviewing the target.",
                ),
                exit_code=3,
                operation=public_operation,
                document_format=document_format,
                yaml_style=yaml_style,
                definition=public_definition,
                request=request,
                sensitive_values=self._sensitive_param_values(context, plan, params),
            )

        outcome_exit_code = 0
        try:
            request = self._app.operations.validate(definition, payload)
            invocation = asyncio.run(
                self._app.operations._invoke_request_with_outcome(definition, request)
            )
            result = invocation.result
            outcome_exit_code = invocation.exit_code
            actions = _provider_actions_for(
                self._action_provider,
                operation=public_operation,
                request=request,
                result=result,
            )
            envelope: BaseModel
            if self._envelope_renderer is None:
                envelope = SuccessEnvelope(
                    command=command,
                    result=result,
                    next_actions=actions,
                )
            else:
                envelope = self._envelope_renderer.output_model.model_validate(
                    self._envelope_renderer.render(
                        Invocation(
                            operation=public_definition,
                            request=public_request(
                                definition,
                                request,
                                sensitive_values=self._sensitive_param_values(
                                    context, plan, params
                                ),
                            ),
                            result=result,
                            error=None,
                            next_actions=actions,
                            budget=self._selected_render_options(
                                document_format, yaml_style
                            ).budget,
                            command=command,
                        )
                    )
                )
            click.echo(
                render(
                    (
                        envelope.model_dump(mode="json", exclude_none=False)
                        if self._envelope_renderer is not None
                        else envelope
                    ),
                    options=self._selected_render_options(document_format, yaml_style),
                ),
                nl=False,
            )
        except OperationInputError as error:
            self._emit_error(
                command,
                self._redact_error(
                    error,
                    plan,
                    raw=tuple(context.meta.get(_RAW_ARGV_KEY, command.raw)),
                    sensitive_values=self._sensitive_param_values(context, plan, params),
                ),
                exit_code=2,
                operation=public_operation,
                document_format=document_format,
                yaml_style=yaml_style,
                definition=public_definition,
                request=request,
                sensitive_values=self._sensitive_param_values(context, plan, params),
            )
        except OperationOutputError as error:
            self._emit_error(
                command,
                error,
                exit_code=70,
                operation=public_operation,
                document_format=document_format,
                yaml_style=yaml_style,
                definition=public_definition,
                request=request,
                sensitive_values=self._sensitive_param_values(context, plan, params),
            )
        except OperationError as error:
            self._emit_error(
                command,
                self._redact_error(
                    error,
                    plan,
                    raw=tuple(context.meta.get(_RAW_ARGV_KEY, command.raw)),
                    sensitive_values=self._sensitive_param_values(context, plan, params),
                ),
                exit_code=self._exit_code_for(error),
                operation=public_operation,
                document_format=document_format,
                yaml_style=yaml_style,
                definition=public_definition,
                request=request,
                sensitive_values=self._sensitive_param_values(context, plan, params),
            )
        except OutputBudgetExceeded as error:
            self._emit_error(
                _compact_command(command),
                OperationError(error.code, str(error), details=(error.details,), fix=error.fix),
                exit_code=70,
                operation=public_operation,
                document_format=document_format,
                yaml_style=yaml_style,
                definition=public_definition,
                request=request,
                sensitive_values=self._sensitive_param_values(context, plan, params),
            )
        except Exception:
            self._emit_error(
                command,
                OperationError(
                    "internal_error",
                    "Operation failed unexpectedly",
                    fix="Retry or inspect application diagnostics.",
                ),
                exit_code=70,
                operation=public_operation,
                document_format=document_format,
                yaml_style=yaml_style,
                definition=public_definition,
                request=request,
                sensitive_values=self._sensitive_param_values(context, plan, params),
            )

        if outcome_exit_code:
            raise click.exceptions.Exit(outcome_exit_code)

    def _payload(
        self,
        context: click.Context,
        plan: CliCommandPlan,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        payload = self._shared_payload(context)
        for field in plan.fields:
            if field.source == "stdin":
                if not params[_stdin_parameter_name(field)]:
                    continue
                value = _read_stdin_field(field)
                params[field.name] = value
                payload[field.name] = value
                continue
            if context.get_parameter_source(field.name) is not ParameterSource.COMMANDLINE:
                continue
            value = params[field.name]
            if field.reference_type is not None:
                value = self._references.decode_type(field.reference_type, value)
            payload[field.name] = value
        return payload

    def _shared_payload(self, context: click.Context) -> dict[str, Any]:
        root = self._surface_context(context)
        payload: dict[str, Any] = {}
        for field in self._shared_fields:
            if root.get_parameter_source(field.name) is not ParameterSource.COMMANDLINE:
                continue
            value = root.params[field.name]
            if field.reference_type is not None:
                value = self._references.decode_type(field.reference_type, value)
            payload[field.name] = value
        return payload

    def _exit_code_for(self, error: OperationError) -> int:
        exit_code = self._operation_error_exit_code(error.code)
        if type(exit_code) is not int or not 1 <= exit_code <= 125:
            raise ValueError("operation_error_exit_code must return an integer from 1 through 125")
        return exit_code

    def _command_view(
        self,
        context: click.Context,
        plan: CliCommandPlan,
        params: dict[str, Any],
        *,
        transport_confirm: bool = False,
    ) -> CommandView:
        arguments: dict[str, Any] = {}
        options: dict[str, Any] = {}
        flags = []
        root = self._surface_context(context)
        for field in self._shared_fields:
            if root.get_parameter_source(field.name) is ParameterSource.COMMANDLINE:
                options[field.name] = _REDACTED if field.sensitive else root.params[field.name]
        for field in plan.fields:
            if field.source == "stdin":
                if params[_stdin_parameter_name(field)]:
                    flags.append(f"{field.name.replace('_', '-')}-stdin")
                continue
            if context.get_parameter_source(field.name) is not ParameterSource.COMMANDLINE:
                continue
            value = _REDACTED if field.sensitive else params[field.name]
            if field.kind == "argument":
                arguments[field.name] = value
            elif field.value_kind == "boolean":
                flags.append(field.name if value is True else f"no-{field.name.replace('_', '-')}")
            else:
                options[field.name] = value
        if transport_confirm:
            flags.append("confirm")
        raw = tuple(context.meta.get(_RAW_ARGV_KEY, (self._app.name, *plan.path)))
        return CommandView(
            raw=_redact_raw(raw, plan, extra_fields=self._shared_fields),
            parsed=ParsedCommand(
                path=plan.path,
                args=arguments,
                options=options,
                flags=tuple(flags),
            ),
        )

    def _surface_context(self, context: click.Context) -> click.Context:
        current: click.Context | None = context
        surface_context: click.Context | None = None
        while current is not None:
            command = current.command
            if isinstance(command, _SurfaceGroup) and command._adapter is self:
                surface_context = current
            current = current.parent
        if surface_context is not None:
            return surface_context
        raise AssertionError("Click adapter context is not mounted in its command tree")

    def _emit_error(
        self,
        command: CommandView,
        error: OperationError,
        *,
        exit_code: int,
        operation: str = "",
        document_format: str,
        yaml_style: str,
        definition: OperationDefinition | None = None,
        request: BaseModel | None = None,
        sensitive_values: tuple[Any, ...] = (),
    ) -> typing.Never:
        try:
            actions = _provider_actions_for(
                self._action_provider,
                operation=operation,
                request=request,
                error=error,
            )
        except Exception:
            actions = NoActions().actions_for(
                operation=operation,
                request=request,
                error=error,
            )
        if self._envelope_renderer is not None and definition is not None:
            invocation = Invocation(
                operation=definition,
                request=(
                    public_request(definition, request, sensitive_values=sensitive_values)
                    if request is not None
                    else None
                ),
                result=None,
                error=error,
                next_actions=actions,
                budget=self._selected_render_options(document_format, yaml_style).budget,
                command=command,
            )
            try:
                envelope = self._envelope_renderer.output_model.model_validate(
                    self._envelope_renderer.render(invocation)
                )
                rendered = render(
                    envelope.model_dump(mode="json", exclude_none=False),
                    options=self._selected_render_options(document_format, yaml_style),
                )
            except OutputBudgetExceeded as budget_error:
                error = OperationError(
                    budget_error.code,
                    str(budget_error),
                    details=(budget_error.details,),
                    fix=budget_error.fix,
                )
                envelope = self._envelope_renderer.output_model.model_validate(
                    self._envelope_renderer.render(invocation.bounded_error(error))
                )
                rendered = render(
                    envelope.model_dump(mode="json", exclude_none=False),
                    options=self._selected_render_options(document_format, yaml_style),
                )
            click.echo(
                rendered,
                nl=False,
            )
            raise click.exceptions.Exit(exit_code)
        outcome = error_outcome(error, next_actions=actions)
        envelope = ErrorEnvelope(
            command=command,
            error=outcome.error,
            fix=outcome.fix,
            next_actions=outcome.next_actions,
        )
        options = self._selected_render_options(document_format, yaml_style)
        try:
            rendered = render(envelope, options=options)
        except OutputBudgetExceeded as budget_error:
            fallback = ErrorEnvelope(
                command=_compact_command(
                    command,
                    max_items=options.budget.max_items,
                ),
                error=error_outcome(
                    OperationError(
                        budget_error.code,
                        str(budget_error),
                        details=(budget_error.details,),
                        fix=budget_error.fix,
                    )
                ).error,
                fix=budget_error.fix,
            )
            try:
                rendered = render_envelope(fallback, options=options)
            except OutputBudgetExceeded:
                emergency = ErrorEnvelope(
                    command=CommandView(
                        raw=("agent-surface",),
                        parsed=ParsedCommand(path=()),
                    ),
                    error=error_outcome(
                        OperationError(
                            budget_error.code,
                            str(budget_error),
                            fix=budget_error.fix,
                        )
                    ).error,
                    fix=budget_error.fix,
                )
                emergency_options = options.model_copy(
                    update={
                        "budget": OutputBudget(
                            max_items=max(20, options.budget.max_items),
                            max_bytes=options.budget.max_bytes,
                        )
                    }
                )
                rendered = render(emergency, options=emergency_options)
        click.echo(rendered, nl=False)
        raise click.exceptions.Exit(exit_code)

    def _emit_parse_error(
        self,
        context: click.Context,
        plan: CliCommandPlan,
        error: click.ClickException,
    ) -> typing.Never:
        raw = tuple(context.meta.get(_RAW_ARGV_KEY, (self._app.name, *plan.path)))
        document_format, yaml_style = _render_choices_from_raw(raw)
        command = CommandView(
            raw=_redact_raw(raw, plan, extra_fields=self._shared_fields),
            parsed=ParsedCommand(path=plan.path),
        )
        public_operation = ".".join(plan.path)
        definition = replace(
            self._app.operations.describe(plan.operation),
            name=public_operation,
        )
        self._emit_error(
            command,
            OperationError(
                "usage_error",
                _redact_text(
                    error.format_message(),
                    _sensitive_raw_values(raw, plan, extra_fields=self._shared_fields),
                ),
                fix=f"Run {self._app.name} operations describe {plan.operation}.",
            ),
            exit_code=2,
            operation=public_operation,
            document_format=document_format,
            yaml_style=yaml_style,
            definition=definition,
        )

    def _emit_group_parse_error(
        self,
        context: click.Context,
        path: tuple[str, ...],
        error: click.UsageError,
    ) -> typing.Never:
        raw = tuple(context.meta.get(_RAW_ARGV_KEY, (self._app.name, *path)))
        document_format, yaml_style = _render_choices_from_raw(raw)
        self._emit_error(
            CommandView(raw=raw, parsed=ParsedCommand(path=path)),
            OperationError(
                "usage_error",
                error.format_message(),
                fix=f"Run {self._app.name} operations list to discover valid commands.",
            ),
            exit_code=2,
            operation=".".join(path),
            document_format=document_format,
            yaml_style=yaml_style,
        )

    def _emit_discovery_parse_error(
        self,
        context: click.Context,
        path: tuple[str, ...],
        error: click.ClickException,
    ) -> typing.Never:
        raw = tuple(context.meta.get(_RAW_ARGV_KEY, (self._app.name, *path)))
        document_format, yaml_style = _render_choices_from_raw(raw)
        self._emit_error(
            CommandView(raw=raw, parsed=ParsedCommand(path=path)),
            OperationError(
                "usage_error",
                error.format_message(),
                fix=f"Run {self._app.name} {path[0]} --help for valid usage.",
            ),
            exit_code=2,
            operation=".".join(path),
            document_format=document_format,
            yaml_style=yaml_style,
        )

    def _selected_render_options(self, document_format: str, yaml_style: str) -> RenderOptions:
        return self._render_options.model_copy(
            update={"format": document_format, "yaml_style": yaml_style}
        )

    def _redact_error(
        self,
        error: OperationError,
        plan: CliCommandPlan,
        *,
        raw: tuple[str, ...],
        sensitive_values: tuple[Any, ...],
    ) -> OperationError:
        fields = (*self._shared_fields, *plan.fields)
        sensitive = {field.name for field in fields if field.sensitive}
        secrets = _sensitive_raw_values(raw, plan, extra_fields=self._shared_fields)

        def redact(value: Any, key: str | None = None) -> Any:
            if key in sensitive:
                return _REDACTED
            if any(type(value) is type(secret) and value == secret for secret in sensitive_values):
                return _REDACTED
            if isinstance(value, dict):
                return {item_key: redact(item, str(item_key)) for item_key, item in value.items()}
            if isinstance(value, tuple):
                return tuple(redact(item) for item in value)
            if isinstance(value, list):
                return [redact(item) for item in value]
            if isinstance(value, str):
                return _redact_text(value, secrets)
            lexical: str | None
            try:
                lexical = encode_scalar(value)
            except ReferenceError:
                lexical = str(value) if isinstance(value, Path) else None
            if lexical is not None and lexical in secrets:
                return _REDACTED
            return value

        details = []
        for item in error.details:
            copied = redact(dict(item))
            location = tuple(copied.get("loc", ()))
            if location and location[0] in sensitive and "input" in copied:
                copied["input"] = _REDACTED
            details.append(copied)
        return OperationError(
            error.code,
            _redact_text(error.message, secrets),
            details=tuple(details),
            fix=_redact_text(error.fix, secrets) if error.fix is not None else None,
            retryable=error.retryable,
        )

    @staticmethod
    def _sensitive_param_values(
        context: click.Context,
        plan: CliCommandPlan,
        params: dict[str, Any],
    ) -> tuple[Any, ...]:
        return tuple(
            params[field.name]
            for field in plan.fields
            if field.sensitive
            and field.name in params
            and (
                params[_stdin_parameter_name(field)]
                if field.source == "stdin"
                else context.get_parameter_source(field.name) is ParameterSource.COMMANDLINE
            )
        )


def build_click_group(
    app: App | ComposedApp,
    *,
    references: ReferenceRegistry | None = None,
    action_provider: ActionProvider | None = None,
    render_options: RenderOptions | None = None,
    argv_provider: Callable[[], Sequence[str]] | None = None,
) -> click.Group:
    if isinstance(app, ComposedApp):
        return ComposedClickAdapter(
            app,
            references=references,
            action_provider=action_provider,
            render_options=render_options,
            argv_provider=argv_provider,
        ).command()
    return ClickAdapter(
        app,
        references=references,
        action_provider=action_provider,
        render_options=render_options,
        argv_provider=argv_provider,
    ).command()


class ComposedClickAdapter:
    """Mount independently configured Click projections into one command tree."""

    def __init__(
        self,
        app: ComposedApp,
        *,
        references: ReferenceRegistry | None = None,
        action_provider: ActionProvider | None = None,
        render_options: RenderOptions | None = None,
        argv_provider: Callable[[], Sequence[str]] | None = None,
    ) -> None:
        self._app = app
        self._defaults: dict[str, Any] = {
            "references": references,
            "action_provider": action_provider,
            "render_options": render_options,
            "argv_provider": argv_provider,
        }

    def command(self) -> click.Group:
        root = _ComposedSurfaceGroup(
            self._app.name,
            help=f"{self._app.name} composed agent surface",
            context_settings={"help_option_names": ["-h", "--help"]},
            params=_render_parameters(),
            app_name=self._app.name,
        )
        mounted: set[tuple[tuple[str, ...], int]] = set()
        for route in sorted(
            self._app.operations(),
            key=lambda item: (len(item.mount_path), item.mount_path, item.public_path),
        ):
            key = (route.mount_path, id(route.app))
            if key in mounted:
                continue
            mounted.add(key)
            options = {name: value for name, value in self._defaults.items() if value is not None}
            options.update(route.click_options)
            command = ClickAdapter(route.app, **options).command()
            _repath_surface_commands(command, route.mount_path)
            command.name = route.mount_path[-1]
            parent: click.Group = root
            for segment in route.mount_path[:-1]:
                existing = parent.commands.get(segment)
                if existing is None:
                    group = click.Group(segment)
                    parent.add_command(group)
                    parent = group
                elif isinstance(existing, click.Group):
                    _relax_group_requirements(existing)
                    parent = existing
                else:  # pragma: no cover - composition rejects leaf collisions
                    raise AssertionError("composed command path became ambiguous")
            parent.add_command(command)
        self._add_discovery(root)
        return root

    def _add_discovery(self, root: click.Group) -> None:
        definitions = tuple(
            replace(route.operation, name=route.public_name) for route in self._app.operations()
        )
        catalog = OperationCatalog(
            cast(OperationRegistry, _PublicOperationRegistry(definitions)),
            discovery_command=(self._app.name, "operations", "list"),
        )
        operations = click.Group("operations", help="Discover composed operations.")

        @click.pass_context
        def list_operations(
            context: click.Context, /, cursor: str | None, limit: int, **params: Any
        ) -> None:
            raw = tuple(context.meta.get(_RAW_ARGV_KEY, (self._app.name, "operations", "list")))
            document_format, yaml_style = _render_choices_from_raw(raw)
            command = CommandView(
                raw=raw,
                parsed=ParsedCommand(
                    path=("operations", "list"), options={"cursor": cursor, "limit": limit}
                ),
            )
            try:
                page = catalog.page(cursor=cursor, budget=OutputBudget(max_items=limit))
                click.echo(
                    render(
                        SuccessEnvelope(command=command, result=page),
                        options=RenderOptions.model_validate(
                            {"format": document_format, "yaml_style": yaml_style}
                        ),
                    ),
                    nl=False,
                )
            except OperationError as error:
                click.echo(
                    render(
                        ErrorEnvelope(
                            command=command, error=error_outcome(error).error, fix=error.fix
                        ),
                        options=RenderOptions.model_validate(
                            {"format": document_format, "yaml_style": yaml_style}
                        ),
                    ),
                    nl=False,
                )
                raise click.exceptions.Exit(2) from None

        @click.pass_context
        def describe_operation(context: click.Context, /, name: str, **params: Any) -> None:
            raw = tuple(context.meta.get(_RAW_ARGV_KEY, (self._app.name, "operations", "describe")))
            document_format, yaml_style = _render_choices_from_raw(raw)
            command = CommandView(
                raw=raw, parsed=ParsedCommand(path=("operations", "describe"), args={"name": name})
            )
            try:
                description = catalog.describe(name)
                click.echo(
                    render(
                        SuccessEnvelope(command=command, result=description),
                        options=RenderOptions.model_validate(
                            {"format": document_format, "yaml_style": yaml_style}
                        ),
                    ),
                    nl=False,
                )
            except OperationError as error:
                click.echo(
                    render(
                        ErrorEnvelope(
                            command=command, error=error_outcome(error).error, fix=error.fix
                        ),
                        options=RenderOptions.model_validate(
                            {"format": document_format, "yaml_style": yaml_style}
                        ),
                    ),
                    nl=False,
                )
                raise click.exceptions.Exit(2) from None

        operations.add_command(
            click.Command(
                "list",
                callback=list_operations,
                params=[*_pagination_parameters(), *_render_parameters()],
            )
        )
        operations.add_command(
            click.Command(
                "describe",
                callback=describe_operation,
                params=[click.Argument(("name",)), *_render_parameters()],
            )
        )
        root.add_command(operations)


class _PublicOperationRegistry:
    def __init__(self, definitions: tuple[OperationDefinition, ...]) -> None:
        self._definitions = definitions
        self._by_name = {definition.name: definition for definition in definitions}

    def list(self) -> tuple[OperationDefinition, ...]:
        return self._definitions

    def describe(self, name: str) -> OperationDefinition:
        definition = self._by_name.get(name)
        if definition is None:
            raise OperationError("operation_not_found", f"No operation is registered as {name}")
        return definition


def _relax_group_requirements(group: click.Group) -> None:
    """Allow a mounted child namespace to contain another independently typed App."""

    for parameter in group.params:
        if isinstance(parameter, click.Option):
            parameter.required = False


def _repath_surface_commands(command: click.Command, prefix: tuple[str, ...]) -> None:
    if isinstance(command, _SurfaceGroup):
        command._path = (*prefix, *command._path)
    if isinstance(command, _SurfaceCommand):
        command._plan = replace(command._plan, path=(*prefix, *command._plan.path))
    if isinstance(command, _SurfaceDiscoveryCommand):
        command._path = (*prefix, *command._path)
    if isinstance(command, click.Group):
        for child in command.commands.values():
            _repath_surface_commands(child, prefix)


class _ComposedSurfaceGroup(click.Group):
    def __init__(self, *args: Any, app_name: str, **kwargs: Any) -> None:
        self._app_name = app_name
        super().__init__(*args, **kwargs)

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: click.Context | None = None,
        **extra: Any,
    ) -> click.Context:
        context = super().make_context(info_name, args, parent=parent, **extra)
        context.meta.setdefault(_RAW_ARGV_KEY, (info_name or self._app_name, *args))
        return context

    def resolve_command(
        self,
        ctx: click.Context,
        args: list[str],
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as error:
            raw = tuple(ctx.meta.get(_RAW_ARGV_KEY, (self._app_name, *args)))
            document_format, yaml_style = _render_choices_from_raw(raw)
            envelope = ErrorEnvelope(
                command=CommandView(raw=raw, parsed=ParsedCommand(path=())),
                error=error_outcome(
                    OperationError(
                        "usage_error",
                        error.format_message(),
                        fix=f"Run {self._app_name} --help to discover commands.",
                    )
                ).error,
                fix=f"Run {self._app_name} --help to discover commands.",
            )
            click.echo(
                render(
                    envelope,
                    options=RenderOptions.model_validate(
                        {"format": document_format, "yaml_style": yaml_style}
                    ),
                ),
                nl=False,
            )
            raise click.exceptions.Exit(2) from None


class _SurfaceGroup(click.Group):
    def __init__(
        self,
        *args: Any,
        adapter: ClickAdapter,
        path: tuple[str, ...],
        **kwargs: Any,
    ) -> None:
        self._adapter = adapter
        self._path = path
        super().__init__(*args, **kwargs)

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: click.Context | None = None,
        **extra: Any,
    ) -> click.Context:
        raw = self._adapter._capture_raw(info_name, args)
        context = super().make_context(info_name, args, parent=parent, **extra)
        context.meta.setdefault(_RAW_ARGV_KEY, raw)
        return context

    def resolve_command(
        self,
        ctx: click.Context,
        args: list[str],
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as error:
            self._adapter._emit_group_parse_error(ctx, self._path, error)


class _SurfaceCommand(click.Command):
    def __init__(
        self,
        *args: Any,
        adapter: ClickAdapter,
        plan: CliCommandPlan,
        **kwargs: Any,
    ) -> None:
        self._adapter = adapter
        self._plan = plan
        super().__init__(*args, **kwargs)

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        try:
            return super().parse_args(ctx, args)
        except click.ClickException as error:
            self._adapter._emit_parse_error(ctx, self._plan, error)


class _SurfaceDiscoveryCommand(click.Command):
    def __init__(
        self,
        *args: Any,
        adapter: ClickAdapter,
        path: tuple[str, ...],
        **kwargs: Any,
    ) -> None:
        self._adapter = adapter
        self._path = path
        super().__init__(*args, **kwargs)

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        try:
            return super().parse_args(ctx, args)
        except click.ClickException as error:
            self._adapter._emit_discovery_parse_error(ctx, self._path, error)


def _render_parameters() -> list[click.Parameter]:
    return [
        click.Option(
            ("--format", "_surface_format"),
            type=click.Choice(("yaml", "json")),
            default="yaml",
            help="Structured document format.",
        ),
        click.Option(
            ("--yaml-style", "_surface_yaml_style"),
            type=click.Choice(("auto", "flow", "block")),
            default="auto",
            help="YAML collection presentation style.",
        ),
    ]


def _pagination_parameters() -> list[click.Parameter]:
    return [
        click.Option(("--cursor",), type=click.STRING, default=None),
        click.Option(
            ("--limit",),
            type=click.IntRange(min=1, max=100),
            default=20,
            show_default=True,
        ),
    ]


def _redact_raw(
    raw: tuple[str, ...],
    plan: CliCommandPlan,
    *,
    extra_fields: tuple[CliFieldPlan, ...] = (),
) -> tuple[str, ...]:
    fields = (*extra_fields, *plan.fields)
    sensitive_values = frozenset(_sensitive_raw_values(raw, plan, extra_fields=extra_fields))
    redacted = tuple(_REDACTED if token in sensitive_values else token for token in raw)
    for field in fields:
        if field.source != "argv" or not field.sensitive or field.kind != "option":
            continue
        for option in field.parameter_decls:
            redacted = tuple(
                f"{option}={_REDACTED}" if token.startswith(f"{option}=") else token
                for token in redacted
            )
    return redacted


def _sensitive_raw_values(
    raw: tuple[str, ...],
    plan: CliCommandPlan,
    *,
    extra_fields: tuple[CliFieldPlan, ...] = (),
) -> tuple[str, ...]:
    options = {
        option: field
        for field in (*extra_fields, *plan.fields)
        if field.source == "argv" and field.kind == "option"
        for option in field.parameter_decls
    }
    arguments = tuple(field for field in plan.fields if field.kind == "argument")
    values: list[str] = []
    argument_index = 0
    index = min(1 + len(plan.path), len(raw))
    positional_only = False
    while index < len(raw):
        token = raw[index]
        if not positional_only and token == "--":
            positional_only = True
            index += 1
            continue
        if not positional_only and token.startswith("--"):
            name, separator, inline_value = token.partition("=")
            field = options.get(name)
            consumes_value = field is not None and field.value_kind != "boolean"
            if field is not None and field.sensitive and consumes_value:
                if separator:
                    values.append(inline_value)
                elif index + 1 < len(raw):
                    values.append(raw[index + 1])
            if not separator and (consumes_value or name in {"--format", "--yaml-style"}):
                index += 2
            else:
                index += 1
            continue
        if argument_index < len(arguments):
            field = arguments[argument_index]
            if field.sensitive:
                values.append(token)
            argument_index += 1
        index += 1
    return tuple(value for value in values if value)


def _redact_text(value: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        value = value.replace(secret, _REDACTED)
    return value


def _render_choices_from_raw(raw: tuple[str, ...]) -> tuple[str, str]:
    document_format = "yaml"
    yaml_style = "auto"
    for index, token in enumerate(raw):
        if token in {"--format", "--output"} and index + 1 < len(raw):
            candidate = raw[index + 1]
            if candidate in {"yaml", "json"}:
                document_format = candidate
        elif token.startswith("--format=") or token.startswith("--output="):
            candidate = token.partition("=")[2]
            if candidate in {"yaml", "json"}:
                document_format = candidate
        elif token == "--yaml-style" and index + 1 < len(raw):
            yaml_style = raw[index + 1]
        elif token.startswith("--yaml-style="):
            yaml_style = token.partition("=")[2]
    return document_format, yaml_style


def _compact_command(command: CommandView, *, max_items: int = 20) -> CommandView:
    marker = "<value omitted: exceeds output budget>"

    def compact(value: Any) -> Any:
        if isinstance(value, str) and len(value.encode("utf-8")) > 256:
            return marker
        if isinstance(value, tuple):
            if len(value) > max_items:
                return (marker,)
            return tuple(compact(item) for item in value)
        if isinstance(value, list):
            if len(value) > max_items:
                return [marker]
            return [compact(item) for item in value]
        if isinstance(value, dict):
            if len(value) > max_items:
                return {"_omitted": marker}
            return {key: compact(item) for key, item in value.items()}
        return value

    return CommandView(
        raw=compact(command.raw),
        parsed=ParsedCommand(
            path=command.parsed.path,
            args=compact(command.parsed.args),
            options=compact(command.parsed.options),
            flags=command.parsed.flags,
        ),
        resolved=command.resolved,
    )


def _click_parameter(
    field: CliFieldPlan,
    *,
    required_override: bool | None = None,
) -> click.Parameter:
    required = field.required if required_override is None else required_override
    parameter_type = _click_type(field)
    if field.kind == "argument":
        return click.Argument(
            field.parameter_decls,
            required=required,
            type=parameter_type,
        )
    declarations = field.parameter_decls
    if field.value_kind == "boolean":
        declarations = tuple(
            f"{declaration}/--no-{declaration[2:]}" for declaration in declarations
        )
    option_kwargs: dict[str, Any] = {}
    if not required:
        option_kwargs["default"] = () if field.multiple else None
    return click.Option(
        (*declarations, field.name),
        required=required,
        type=parameter_type,
        multiple=field.multiple,
        is_flag=field.value_kind == "boolean",
        help=field.help,
        show_default=False,
        **option_kwargs,
    )


def _option_declarations(field: CliFieldPlan) -> tuple[str, ...]:
    declarations = field.parameter_decls
    if field.value_kind != "boolean":
        return declarations
    return (*declarations, *(f"--no-{declaration[2:]}" for declaration in declarations))


def _stdin_parameters(fields: tuple[CliFieldPlan, ...]) -> list[click.Option]:
    parameters = []
    for field in fields:
        if field.source != "stdin":
            continue
        assert field.stdin_flag is not None  # compiler validates stdin field plans
        parameters.append(
            click.Option(
                (field.stdin_flag, _stdin_parameter_name(field)),
                is_flag=True,
                default=False,
                required=field.required,
                help=f"Read sensitive {field.name} from standard input.",
            )
        )
    return parameters


def _stdin_parameter_name(field: CliFieldPlan) -> str:
    return f"_surface_stdin_{field.name}"


def _read_stdin_field(field: CliFieldPlan) -> str:
    assert field.stdin_max_bytes is not None  # compiler validates stdin field plans
    value = sys.stdin.buffer.read(field.stdin_max_bytes + 1)
    if not value:
        raise OperationError(
            "stdin_missing",
            f"No value was provided on stdin for {field.name}",
            fix=f"Pipe one value and retry with {field.stdin_flag}.",
        )
    if len(value) > field.stdin_max_bytes:
        raise OperationError(
            "stdin_too_large",
            f"Stdin value for {field.name} exceeds {field.stdin_max_bytes} bytes",
            fix="Pipe a smaller single value or raise cli.max_bytes deliberately.",
        )

    normalized = value
    if normalized.endswith(b"\n"):
        normalized = normalized[:-1]
        if normalized.endswith(b"\r"):
            normalized = normalized[:-1]
    if b"\n" in normalized or b"\r" in normalized:
        raise OperationError(
            "stdin_multiple_values",
            f"Stdin for {field.name} must contain exactly one value",
            fix="Pipe one value followed by at most one trailing newline.",
        )
    if not normalized:
        raise OperationError(
            "stdin_empty",
            f"Stdin value for {field.name} is empty",
            fix="Pipe one non-empty value and retry.",
        )
    try:
        return (normalized if field.strip_trailing_newline else value).decode("utf-8")
    except UnicodeDecodeError:
        raise OperationError(
            "stdin_invalid_encoding",
            f"Stdin value for {field.name} must be UTF-8 text",
            fix="Pipe UTF-8 text and retry.",
        ) from None


def _click_type(field: CliFieldPlan) -> click.ParamType[Any]:
    if field.choices:
        return click.Choice(field.choices, case_sensitive=True)
    if field.value_kind == "integer" and (field.minimum is not None or field.maximum is not None):
        return click.IntRange(min=field.minimum, max=field.maximum)
    return {
        "boolean": click.BOOL,
        "float": _FINITE_FLOAT,
        "integer": click.INT,
        "path": click.Path(path_type=str),
        "reference": click.STRING,
        "string": click.STRING,
    }[field.value_kind]


def _integer_bounds(field: Any) -> tuple[int | None, int | None]:
    minimum: int | None = None
    maximum: int | None = None
    for constraint in field.metadata:
        ge = getattr(constraint, "ge", None)
        le = getattr(constraint, "le", None)
        if type(ge) is int:
            minimum = ge
        if type(le) is int:
            maximum = le
    return minimum, maximum


class _FiniteFloat(click.ParamType[float]):
    name = "float"

    def convert(
        self,
        value: Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> float:
        converted = click.FLOAT.convert(value, param, ctx)
        if not math.isfinite(converted):
            self.fail(f"{value!r} is not a finite float", param, ctx)
        return converted


_FINITE_FLOAT = _FiniteFloat()


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
