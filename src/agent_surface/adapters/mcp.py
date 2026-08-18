"""Optional native MCP v2 projection of the typed operation registry."""

from typing import Any

try:
    from mcp.server.lowlevel import Server
except ModuleNotFoundError as error:  # pragma: no cover - exercised in subprocess isolation
    raise ModuleNotFoundError(
        "MCP support is optional; install it with pip install 'agent-surface[mcp]'"
    ) from error

from agent_surface.app import App


class MCPAdapter:
    """Own the native MCP server projected from one application."""

    def __init__(self, app: App) -> None:
        self._app = app
        self._server: Server[Any] = Server(app.name, version=app.version)

    @property
    def server(self) -> Server[Any]:
        return self._server


__all__ = ["MCPAdapter"]
