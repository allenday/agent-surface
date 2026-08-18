"""Optional native MCP v2 projection of the typed operation registry."""

import base64
import binascii
from dataclasses import dataclass
from typing import Any

try:
    import mcp_types as types
    from mcp.server.lowlevel import Server
    from mcp.shared.exceptions import MCPError
except ModuleNotFoundError as error:  # pragma: no cover - exercised in subprocess isolation
    raise ModuleNotFoundError(
        "MCP support is optional; install it with pip install 'agent-surface[mcp]'"
    ) from error

from agent_surface.app import App
from agent_surface.contracts import SuccessOutcome
from agent_surface.operations import OperationDefinition


@dataclass(frozen=True, slots=True)
class MCPToolPlan:
    operation: str
    tool: types.Tool


class MCPAdapter:
    """Own the native MCP server projected from one application."""

    def __init__(self, app: App, *, page_size: int = 20) -> None:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        self._app = app
        self._page_size = page_size
        self._plans = tuple(self._compile_tool(item) for item in app.operations.list())
        self._server: Server[Any] = Server(
            app.name,
            version=app.version,
            on_list_tools=self._list_tools,
        )

    @property
    def server(self) -> Server[Any]:
        return self._server

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

    @staticmethod
    def _compile_tool(definition: OperationDefinition) -> MCPToolPlan:
        outcome_model = SuccessOutcome[definition.output_model]  # type: ignore[name-defined]
        output_schema = outcome_model.model_json_schema(
            mode="serialization"
        )
        return MCPToolPlan(
            operation=definition.name,
            tool=types.Tool(
                name=definition.name,
                description=definition.summary,
                input_schema=definition.input_model.model_json_schema(mode="validation"),
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
