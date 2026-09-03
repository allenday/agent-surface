"""Optional native MCP v2 projection of the typed operation registry."""

import base64
import binascii
import json
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Any, cast

from pydantic import BaseModel

try:
    import mcp_types as types
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server
    from mcp.shared.exceptions import MCPError
except ModuleNotFoundError as error:  # pragma: no cover - exercised in subprocess isolation
    raise ModuleNotFoundError(
        "MCP support is optional; install it with pip install 'agent-surface[mcp]'"
    ) from error

from agent_surface.app import App
from agent_surface.budgets import OutputBudgetExceeded
from agent_surface.composition import ComposedApp
from agent_surface.contracts import ErrorOutcome, SuccessOutcome
from agent_surface.envelopes import CanonicalEnvelopeRenderer, Invocation, public_request
from agent_surface.operations import OperationDefinition, OperationError
from agent_surface.outcomes import (
    ActionProvider,
    NoActions,
    _provider_actions_for,
    error_outcome,
    success_outcome,
)
from agent_surface.references import InvalidReference, ReferenceError, ReferenceRegistry
from agent_surface.rendering import RenderOptions, render

_MIN_MCP_BYTES = 1_024


@dataclass(frozen=True, slots=True)
class MCPToolPlan:
    operation: str
    tool: types.Tool


class MCPAdapter:
    """Own the native MCP server projected from one application."""

    def __init__(
        self,
        app: App | ComposedApp,
        *,
        page_size: int = 20,
        references: ReferenceRegistry | None = None,
        action_provider: ActionProvider | None = None,
        render_options: RenderOptions | None = None,
        envelope_renderer: CanonicalEnvelopeRenderer | None = None,
    ) -> None:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        self._app = app
        self._references = references or ReferenceRegistry()
        self._action_provider = action_provider or NoActions()
        self._render_options = render_options or RenderOptions()
        self._envelope_renderer = envelope_renderer
        if self._render_options.budget.max_bytes < _MIN_MCP_BYTES:
            raise ValueError(
                f"MCP output budget must be at least {_MIN_MCP_BYTES} bytes so a "
                "structured error can always be emitted"
            )
        self._page_size = page_size
        self._composition_defaults = {
            "page_size": page_size,
            "references": references,
            "action_provider": action_provider,
            "render_options": render_options,
            "envelope_renderer": envelope_renderer,
        }
        self._plans: tuple[MCPToolPlan, ...]
        self._definitions: dict[str, OperationDefinition]
        self._composed_adapters: dict[str, tuple[MCPAdapter, str]] | None = None
        if isinstance(app, ComposedApp):
            dispatch: dict[str, tuple[MCPAdapter, str]] = {}
            plans: list[MCPToolPlan] = []
            mounted: set[tuple[tuple[str, ...], int]] = set()
            for route in app.operations():
                key = (route.mount_path, id(route.app))
                if key in mounted:
                    continue
                mounted.add(key)
                options = {
                    name: value
                    for name, value in self._composition_defaults.items()
                    if value is not None
                }
                options.update(route.options)
                adapter = MCPAdapter(route.app, **cast(Any, options))
                for plan in adapter._plans:
                    public_name = ".".join((*route.mount_path, *plan.operation.split(".")))
                    dispatch[public_name] = (adapter, plan.operation)
                    plans.append(
                        MCPToolPlan(
                            operation=public_name,
                            tool=plan.tool.model_copy(update={"name": public_name}),
                        )
                    )
            self._plans = tuple(sorted(plans, key=lambda plan: plan.operation))
            self._definitions = {}
            self._composed_adapters = dispatch
        else:
            self._plans = tuple(self._compile_tool(item) for item in app.operations.list())
            self._definitions = {item.name: item for item in app.operations.list()}
        self._server: Server[Any] = Server(
            app.name,
            version=app.version,
            on_list_tools=self._list_tools,
            on_call_tool=self._call_tool,
        )

    @classmethod
    def compose(
        cls,
        name: str,
        *adapters: "MCPAdapter",
        version: str = "0.1.0",
        page_size: int = 20,
    ) -> "MCPAdapter":
        """Project existing adapters through one MCP server.

        Each operation remains bound to its source adapter, preserving that
        adapter's references, action provider, renderer, and error policy.
        """

        if not adapters:
            raise ValueError("MCP composition requires at least one adapter")
        if page_size < 1:
            raise ValueError("page_size must be positive")

        dispatch: dict[str, MCPAdapter] = {}
        plans: list[MCPToolPlan] = []
        for adapter in adapters:
            for plan in adapter._plans:
                if plan.operation in dispatch:
                    raise ValueError(f"Duplicate MCP tool name: {plan.operation}")
                dispatch[plan.operation] = adapter
                plans.append(plan)

        composed = cls.__new__(cls)
        composed._app = App(name, version=version)
        composed._references = ReferenceRegistry()
        composed._action_provider = NoActions()
        composed._render_options = RenderOptions()
        composed._envelope_renderer = None
        composed._page_size = page_size
        composed._plans = tuple(sorted(plans, key=lambda plan: plan.operation))
        composed._definitions = {}
        composed._composed_adapters = {
            name: (adapter, name) for name, adapter in dispatch.items()
        }
        composed._server = Server(
            name,
            version=version,
            on_list_tools=composed._list_tools,
            on_call_tool=composed._call_tool,
        )
        return composed

    @property
    def server(self) -> Server[Any]:
        return self._server

    async def run_stdio(self) -> None:
        """Serve MCP over the SDK's stdio transport until the stream closes."""

        async with stdio_server() as (read_stream, write_stream):
            await self._server.run(
                read_stream,
                write_stream,
                self._server.create_initialization_options(),
            )

    def streamable_http_app(self, **kwargs: Any) -> Any:
        """Return the SDK-owned Streamable HTTP ASGI application."""

        return self._server.streamable_http_app(**kwargs)

    async def _list_tools(
        self,
        context: Any,
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        del context
        cursor = params.cursor if params is not None else None
        offset = 0 if cursor is None else _decode_cursor(cursor)
        if offset >= len(self._plans) and cursor is not None:
            raise MCPError(types.INVALID_PARAMS, "Tool cursor is invalid or out of range")
        selected = self._plans[offset : offset + self._page_size]
        next_offset = offset + len(selected)
        next_cursor = _encode_cursor(next_offset) if next_offset < len(self._plans) else None
        return types.ListToolsResult(
            tools=[plan.tool for plan in selected],
            next_cursor=next_cursor,
        )

    async def _call_tool(
        self,
        context: Any,
        params: types.CallToolRequestParams,
        *,
        public_operation: str | None = None,
    ) -> types.CallToolResult:
        if self._composed_adapters is not None:
            mounted = self._composed_adapters.get(params.name)
            if mounted is None:
                raise MCPError(types.INVALID_PARAMS, f"Unknown tool: {params.name}")
            adapter, operation = mounted
            return await adapter._call_tool(
                context,
                params.model_copy(update={"name": operation}),
                public_operation=params.name,
            )
        del context
        assert isinstance(self._app, App)
        source_definition = self._definitions.get(params.name)
        if source_definition is None:
            raise MCPError(types.INVALID_PARAMS, f"Unknown tool: {params.name}")
        definition = (
            replace(source_definition, name=public_operation)
            if public_operation is not None
            else source_definition
        )
        arguments = dict(params.arguments or {})
        confirm_field = definition.input_model.model_fields.get("confirm")
        confirmed = arguments.get("confirm") is True
        if definition.destructive and not confirmed:
            return self._error_result(
                OperationError(
                    "confirmation_required",
                    "Destructive operation requires explicit confirmation",
                    fix="Retry with confirm: true after reviewing the target.",
                ),
                operation=definition.name,
                definition=definition,
            )
        if definition.destructive and confirm_field is None:
            arguments.pop("confirm", None)
        request: BaseModel | None = None
        try:
            arguments = self._decode_references(definition, arguments)
            request = self._app.operations.validate(definition, arguments)
            result = (
                await self._app.operations._invoke_request_with_outcome(definition, request)
            ).result
            try:
                actions = _provider_actions_for(
                    self._action_provider,
                    operation=definition.name,
                    request=request,
                    result=result,
                )
            except Exception:
                return self._error_result(
                    OperationError(
                        "internal_error",
                        "Action provider failed unexpectedly",
                        fix="Retry or inspect application diagnostics.",
                    ),
                    operation=definition.name,
                    include_actions=False,
                    definition=definition,
                    request=request,
                )
            return self._mcp_result(
                Invocation(
                    operation=definition,
                    request=public_request(definition, request),
                    result=result,
                    error=None,
                    next_actions=actions,
                    budget=self._render_options.budget,
                ),
                is_error=False,
            )
        except ReferenceError as error:
            return self._error_result(
                self._redact_error(
                    OperationError(error.code, str(error), fix=error.fix),
                    definition,
                    params.arguments or {},
                ),
                operation=definition.name,
                definition=definition,
                request=request,
            )
        except OperationError as error:
            return self._error_result(
                self._redact_error(error, definition, params.arguments or {}),
                operation=definition.name,
                definition=definition,
                request=request,
            )
        except Exception:
            return self._error_result(
                OperationError(
                    "internal_error",
                    "Operation failed unexpectedly",
                    fix="Retry or inspect application diagnostics.",
                ),
                operation=definition.name,
                include_actions=False,
                definition=definition,
                request=request,
            )

    def _decode_references(
        self,
        definition: OperationDefinition,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        decoded = dict(arguments)
        for name, field in definition.input_model.model_fields.items():
            annotation = field.annotation
            if (
                name in decoded
                and isinstance(annotation, type)
                and self._references.supports_type(annotation)
            ):
                try:
                    decoded[name] = self._references.decode_type(annotation, decoded[name])
                except ReferenceError:
                    raise
                except Exception as error:
                    raise InvalidReference(
                        "Reference token could not be decoded",
                        fix="Use an ID produced by the registered reference codec.",
                    ) from error
        return decoded

    def _error_result(
        self,
        error: OperationError,
        *,
        operation: str,
        include_actions: bool = True,
        definition: OperationDefinition | None = None,
        request: BaseModel | None = None,
    ) -> types.CallToolResult:
        actions = NoActions().actions_for(
            operation=operation,
            request=request,
            error=error,
        )
        if include_actions:
            with suppress(Exception):
                actions = _provider_actions_for(
                    self._action_provider,
                    operation=operation,
                    request=request,
                    error=error,
                )
        if definition is None:
            return self._mcp_result(error_outcome(error, next_actions=actions), is_error=True)
        return self._mcp_result(
            Invocation(
                operation=definition,
                request=public_request(definition, request) if request is not None else None,
                result=None,
                error=error,
                next_actions=actions,
                budget=self._render_options.budget,
            ),
            is_error=True,
        )

    @staticmethod
    def _redact_error(
        error: OperationError,
        definition: OperationDefinition,
        arguments: dict[str, Any],
    ) -> OperationError:
        sensitive = {
            name
            for name, field in definition.input_model.model_fields.items()
            if isinstance(field.json_schema_extra, dict)
            and field.json_schema_extra.get("sensitive") is True
        }
        values = tuple(arguments[name] for name in sensitive if name in arguments)
        string_secrets = tuple(
            value for value in values if isinstance(value, str) and value
        )

        def redact(value: Any, key: str | None = None) -> Any:
            if key in sensitive:
                return "<redacted>"
            if any(type(value) is type(secret) and value == secret for secret in values):
                return "<redacted>"
            if isinstance(value, dict):
                return {
                    str(item_key): redact(item, str(item_key))
                    for item_key, item in value.items()
                }
            if isinstance(value, tuple):
                return tuple(redact(item) for item in value)
            if isinstance(value, list):
                return [redact(item) for item in value]
            if isinstance(value, str):
                for secret in string_secrets:
                    value = value.replace(secret, "<redacted>")
            return value

        return OperationError(
            error.code,
            redact(error.message),
            details=tuple(redact(dict(item)) for item in error.details),
            fix=redact(error.fix) if error.fix is not None else None,
            retryable=error.retryable,
        )

    def _mcp_result(
        self,
        outcome: SuccessOutcome[Any] | ErrorOutcome | Invocation,
        *,
        is_error: bool,
    ) -> types.CallToolResult:
        selected = outcome
        try:
            text, document = self._render_payload(selected)
        except OutputBudgetExceeded as error:
            budget_error = OperationError(
                error.code,
                str(error),
                details=(error.details,),
                fix=error.fix,
            )
            selected = (
                selected.bounded_error(budget_error)
                if isinstance(selected, Invocation)
                else error_outcome(budget_error)
            )
            text, document = self._render_payload(selected)
            is_error = True
        return types.CallToolResult(
            content=[types.TextContent(text=text)],
            structured_content=document,
            is_error=is_error,
        )

    def _render_payload(
        self,
        outcome: SuccessOutcome[Any] | ErrorOutcome | Invocation,
    ) -> tuple[str, dict[str, Any]]:
        if isinstance(outcome, Invocation) and self._envelope_renderer is not None:
            document_model = self._envelope_renderer.output_model.model_validate(
                self._envelope_renderer.render(outcome)
            )
        elif isinstance(outcome, Invocation):
            document_model = (
                error_outcome(outcome.error, next_actions=outcome.next_actions)
                if outcome.error is not None
                else success_outcome(outcome.result, next_actions=outcome.next_actions)
            )
        else:
            document_model = outcome
        text = render(document_model, options=self._render_options)
        document = document_model.model_dump(
            mode="json",
            exclude_none=not (
                isinstance(outcome, Invocation) and self._envelope_renderer is not None
            ),
        )
        structured = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        measured = len(text.encode("utf-8")) + len(structured.encode("utf-8"))
        if measured > self._render_options.budget.max_bytes:
            raise OutputBudgetExceeded(
                code="response_too_large",
                message="MCP public content exceeds the byte budget",
                details={
                    "measured_bytes": measured,
                    "max_bytes": self._render_options.budget.max_bytes,
                },
                fix="Retry with a lower item limit or a narrower detail level.",
            )
        return text, document

    def _compile_tool(self, definition: OperationDefinition) -> MCPToolPlan:
        outcome_model = (
            self._envelope_renderer.output_model
            if self._envelope_renderer is not None
            else SuccessOutcome[definition.output_model]  # type: ignore[name-defined]
        )
        output_schema = outcome_model.model_json_schema(mode="serialization")
        input_schema = definition.input_model.model_json_schema(mode="validation")
        properties = input_schema.setdefault("properties", {})
        for name, field in definition.input_model.model_fields.items():
            annotation = field.annotation
            if isinstance(annotation, type) and self._references.supports_type(annotation):
                original = properties.get(name, {})
                properties[name] = {
                    key: original[key]
                    for key in ("title", "description")
                    if key in original
                } | {"type": "string"}
        if definition.destructive:
            confirm_schema = properties.get("confirm")
            if confirm_schema is not None and confirm_schema.get("type") != "boolean":
                raise ValueError("Destructive operation confirm field must be boolean")
            properties["confirm"] = {
                "type": "boolean",
                "const": True,
                "description": "Explicitly confirm this destructive operation.",
            }
            required = input_schema.setdefault("required", [])
            if "confirm" not in required:
                required.append("confirm")
        return MCPToolPlan(
            operation=definition.name,
            tool=types.Tool(
                name=definition.name,
                description=definition.summary,
                input_schema=input_schema,
                output_schema=output_schema,
                annotations=types.ToolAnnotations(
                    read_only_hint=definition.read_only,
                    destructive_hint=definition.destructive,
                    idempotent_hint=definition.idempotent,
                    open_world_hint=definition.open_world,
                ),
            ),
        )


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"v1:{offset}".encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> int:
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(cursor + padding, altchars=b"-_", validate=True).decode()
        version, raw_offset = decoded.split(":", 1)
        offset = int(raw_offset)
        if version != "v1" or offset < 0:
            raise ValueError
        return offset
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise MCPError(types.INVALID_PARAMS, "Tool cursor is invalid") from error


__all__ = ["MCPAdapter", "MCPToolPlan"]
