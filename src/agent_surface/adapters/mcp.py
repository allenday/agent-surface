"""Optional native MCP v2 projection of the typed operation registry."""

import base64
import binascii
import json
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

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
from agent_surface.contracts import ErrorOutcome, SuccessOutcome
from agent_surface.operations import OperationDefinition, OperationError
from agent_surface.outcomes import ActionProvider, NoActions, error_outcome, success_outcome
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
        app: App,
        *,
        page_size: int = 20,
        references: ReferenceRegistry | None = None,
        action_provider: ActionProvider | None = None,
        render_options: RenderOptions | None = None,
    ) -> None:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        self._app = app
        self._references = references or ReferenceRegistry()
        self._action_provider = action_provider or NoActions()
        self._render_options = render_options or RenderOptions()
        if self._render_options.budget.max_bytes < _MIN_MCP_BYTES:
            raise ValueError(
                f"MCP output budget must be at least {_MIN_MCP_BYTES} bytes so a "
                "structured error can always be emitted"
            )
        self._page_size = page_size
        self._plans = tuple(self._compile_tool(item) for item in app.operations.list())
        self._definitions = {item.name: item for item in app.operations.list()}
        self._server: Server[Any] = Server(
            app.name,
            version=app.version,
            on_list_tools=self._list_tools,
            on_call_tool=self._call_tool,
        )

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
    ) -> types.CallToolResult:
        del context
        definition = self._definitions.get(params.name)
        if definition is None:
            raise MCPError(types.INVALID_PARAMS, f"Unknown tool: {params.name}")
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
            )
        if definition.destructive and confirm_field is None:
            arguments.pop("confirm", None)
        try:
            arguments = self._decode_references(definition, arguments)
            result = await self._app.operations.invoke(definition.name, arguments)
            try:
                actions = self._action_provider.actions_for(
                    operation=definition.name,
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
                )
            return self._mcp_result(success_outcome(result, next_actions=actions), is_error=False)
        except ReferenceError as error:
            return self._error_result(
                OperationError(error.code, str(error), fix=error.fix),
                operation=definition.name,
            )
        except OperationError as error:
            return self._error_result(
                self._redact_error(error, definition, params.arguments or {}),
                operation=definition.name,
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
    ) -> types.CallToolResult:
        actions = NoActions().actions_for(operation=operation, error=error)
        if include_actions:
            with suppress(Exception):
                actions = self._action_provider.actions_for(operation=operation, error=error)
        return self._mcp_result(error_outcome(error, next_actions=actions), is_error=True)

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
        outcome: SuccessOutcome[Any] | ErrorOutcome,
        *,
        is_error: bool,
    ) -> types.CallToolResult:
        selected = outcome
        try:
            text, document = self._render_payload(selected)
        except OutputBudgetExceeded as error:
            selected = error_outcome(
                OperationError(error.code, str(error), details=(error.details,), fix=error.fix)
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
        outcome: SuccessOutcome[Any] | ErrorOutcome,
    ) -> tuple[str, dict[str, Any]]:
        text = render(outcome, options=self._render_options)
        document = outcome.model_dump(mode="json", exclude_none=True)
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
        outcome_model = SuccessOutcome[definition.output_model]  # type: ignore[name-defined]
        output_schema = outcome_model.model_json_schema(
            mode="serialization"
        )
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
