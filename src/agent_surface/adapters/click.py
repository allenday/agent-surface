"""Compile registered operations into an immutable Click projection plan."""

import asyncio
import inspect
import types
import typing
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

import click
from click.core import ParameterSource

from agent_surface.app import App
from agent_surface.budgets import OutputBudgetExceeded
from agent_surface.contracts import CommandView, ErrorEnvelope, ParsedCommand, SuccessEnvelope
from agent_surface.operations import (
    OperationDefinition,
    OperationError,
    OperationInputError,
    OperationOutputError,
    OperationRegistry,
)
from agent_surface.outcomes import ActionProvider, NoActions, error_outcome
from agent_surface.references import ReferenceRegistry
from agent_surface.rendering import RenderOptions, render, render_envelope

CliParameterKind = Literal["argument", "option"]
CliValueKind = Literal["boolean", "float", "integer", "path", "reference", "string"]

_RESERVED_ROOTS = frozenset({"actions", "operations"})
_RAW_ARGV_KEY = "agent_surface.raw_argv"
_REDACTED = "<redacted>"


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
        action_provider: ActionProvider | None = None,
        render_options: RenderOptions | None = None,
    ) -> None:
        self._app = app
        self._references = references or ReferenceRegistry()
        self._action_provider = action_provider or NoActions()
        self._render_options = render_options or RenderOptions()
        self._plans = CliPlanCompiler(
            app.operations,
            references=self._references,
        ).compile()

    def command(self) -> click.Group:
        root = _SurfaceGroup(
            name=self._app.name,
            help=f"{self._app.name} agent surface",
            context_settings={"help_option_names": ["-h", "--help"]},
        )
        for plan in self._plans:
            parent: click.Group = root
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

    def _leaf_command(self, plan: CliCommandPlan) -> click.Command:
        @click.pass_context
        def callback(context: click.Context, /, **params: Any) -> None:
            self._invoke(context, plan, params)

        parameters = [_click_parameter(field) for field in plan.fields]
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

        return _SurfaceCommand(
            name=plan.path[-1],
            callback=callback,
            params=parameters,
            help=plan.summary,
            adapter=self,
            plan=plan,
        )

    def _invoke(
        self,
        context: click.Context,
        plan: CliCommandPlan,
        params: dict[str, Any],
    ) -> None:
        document_format = params.pop("_surface_format")
        yaml_style = params.pop("_surface_yaml_style")
        transport_confirm = params.pop("_surface_confirm", False)
        command = self._command_view(context, plan, params)
        payload = self._payload(context, plan, params)
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
                document_format=document_format,
                yaml_style=yaml_style,
            )

        try:
            result = asyncio.run(self._app.operations.invoke(plan.operation, payload))
            actions = self._action_provider.actions_for(
                operation=plan.operation,
                result=result,
            )
            envelope = SuccessEnvelope(
                command=command,
                result=result,
                next_actions=actions,
            )
            click.echo(
                render(
                    envelope,
                    options=self._selected_render_options(document_format, yaml_style),
                ),
                nl=False,
            )
        except OperationInputError as error:
            self._emit_error(
                command,
                self._redact_error(error, plan),
                exit_code=2,
                document_format=document_format,
                yaml_style=yaml_style,
            )
        except OperationOutputError as error:
            self._emit_error(
                command,
                error,
                exit_code=70,
                document_format=document_format,
                yaml_style=yaml_style,
            )
        except OperationError as error:
            self._emit_error(
                command,
                error,
                exit_code=4,
                document_format=document_format,
                yaml_style=yaml_style,
            )
        except OutputBudgetExceeded as error:
            self._emit_error(
                _compact_command(command),
                OperationError(error.code, str(error), details=(error.details,), fix=error.fix),
                exit_code=70,
                operation=plan.operation,
                document_format=document_format,
                yaml_style=yaml_style,
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
                operation=plan.operation,
                document_format=document_format,
                yaml_style=yaml_style,
            )

    def _payload(
        self,
        context: click.Context,
        plan: CliCommandPlan,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for field in plan.fields:
            if context.get_parameter_source(field.name) is not ParameterSource.COMMANDLINE:
                continue
            value = params[field.name]
            if field.reference_type is not None:
                value = self._references.decode_type(field.reference_type, value)
            payload[field.name] = value
        return payload

    def _command_view(
        self,
        context: click.Context,
        plan: CliCommandPlan,
        params: dict[str, Any],
    ) -> CommandView:
        arguments: dict[str, Any] = {}
        options: dict[str, Any] = {}
        flags = []
        for field in plan.fields:
            if context.get_parameter_source(field.name) is not ParameterSource.COMMANDLINE:
                continue
            value = _REDACTED if field.sensitive else params[field.name]
            if field.kind == "argument":
                arguments[field.name] = value
            elif field.value_kind == "boolean":
                flags.append(field.name if value is True else f"no-{field.name.replace('_', '-')}")
            else:
                options[field.name] = value
        raw = tuple(context.meta.get(_RAW_ARGV_KEY, (self._app.name, *plan.path)))
        return CommandView(
            raw=_redact_raw(raw, plan),
            parsed=ParsedCommand(
                path=plan.path,
                args=arguments,
                options=options,
                flags=tuple(flags),
            ),
        )

    def _emit_error(
        self,
        command: CommandView,
        error: OperationError,
        *,
        exit_code: int,
        operation: str = "",
        document_format: str,
        yaml_style: str,
    ) -> typing.Never:
        actions = self._action_provider.actions_for(
            operation=operation,
            error=error,
        )
        outcome = error_outcome(error, next_actions=actions)
        envelope = ErrorEnvelope(
            command=command,
            error=outcome.error,
            fix=outcome.fix,
            next_actions=outcome.next_actions,
        )
        click.echo(
            render_envelope(
                envelope,
                options=self._selected_render_options(document_format, yaml_style),
            ),
            nl=False,
        )
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
            raw=_redact_raw(raw, plan),
            parsed=ParsedCommand(path=plan.path),
        )
        code = {
            click.MissingParameter: "missing_parameter",
            click.BadParameter: "invalid_value",
            click.NoSuchOption: "unknown_option",
        }.get(type(error), "invalid_command")
        self._emit_error(
            command,
            OperationError(
                code,
                error.format_message(),
                fix=f"Run {self._app.name} operations describe {plan.operation}.",
            ),
            exit_code=2,
            operation=plan.operation,
            document_format=document_format,
            yaml_style=yaml_style,
        )

    def _selected_render_options(self, document_format: str, yaml_style: str) -> RenderOptions:
        return self._render_options.model_copy(
            update={"format": document_format, "yaml_style": yaml_style}
        )

    @staticmethod
    def _redact_error(error: OperationError, plan: CliCommandPlan) -> OperationError:
        sensitive = {field.name for field in plan.fields if field.sensitive}
        details = []
        for item in error.details:
            copied = dict(item)
            location = tuple(copied.get("loc", ()))
            if location and location[0] in sensitive and "input" in copied:
                copied["input"] = _REDACTED
            details.append(copied)
        return OperationError(
            error.code,
            error.message,
            details=tuple(details),
            fix=error.fix,
            retryable=error.retryable,
        )


def build_click_group(
    app: App,
    *,
    references: ReferenceRegistry | None = None,
    action_provider: ActionProvider | None = None,
    render_options: RenderOptions | None = None,
) -> click.Group:
    return ClickAdapter(
        app,
        references=references,
        action_provider=action_provider,
        render_options=render_options,
    ).command()


class _SurfaceGroup(click.Group):
    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: click.Context | None = None,
        **extra: Any,
    ) -> click.Context:
        raw = (info_name or self.name or "agent-surface", *tuple(args))
        context = super().make_context(info_name, args, parent=parent, **extra)
        context.meta.setdefault(_RAW_ARGV_KEY, raw)
        return context


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


def _redact_raw(raw: tuple[str, ...], plan: CliCommandPlan) -> tuple[str, ...]:
    sensitive_options = {
        field.parameter_decls[0]
        for field in plan.fields
        if field.sensitive and field.kind == "option"
    }
    redacted = list(raw)
    redact_next = False
    for index, token in enumerate(redacted):
        if redact_next:
            redacted[index] = _REDACTED
            redact_next = False
            continue
        if token in sensitive_options:
            redact_next = True
            continue
        for option in sensitive_options:
            if token.startswith(f"{option}="):
                redacted[index] = f"{option}={_REDACTED}"
                break
    return tuple(redacted)


def _render_choices_from_raw(raw: tuple[str, ...]) -> tuple[str, str]:
    document_format = "yaml"
    yaml_style = "auto"
    for index, token in enumerate(raw):
        if token == "--format" and index + 1 < len(raw):
            document_format = raw[index + 1]
        elif token.startswith("--format="):
            document_format = token.partition("=")[2]
        elif token == "--yaml-style" and index + 1 < len(raw):
            yaml_style = raw[index + 1]
        elif token.startswith("--yaml-style="):
            yaml_style = token.partition("=")[2]
    return document_format, yaml_style


def _compact_command(command: CommandView) -> CommandView:
    marker = "<value omitted: exceeds output budget>"

    def compact(value: Any) -> Any:
        if isinstance(value, str) and len(value.encode("utf-8")) > 256:
            return marker
        if isinstance(value, tuple):
            return tuple(compact(item) for item in value)
        if isinstance(value, dict):
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
    option_kwargs: dict[str, Any] = {}
    if not field.required:
        option_kwargs["default"] = () if field.multiple else None
    return click.Option(
        declarations,
        required=field.required,
        type=parameter_type,
        multiple=field.multiple,
        is_flag=field.value_kind == "boolean",
        help=field.help,
        show_default=False,
        **option_kwargs,
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
