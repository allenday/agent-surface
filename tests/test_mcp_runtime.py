import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel
from starlette.applications import Starlette

from agent_surface import App
from agent_surface.adapters.mcp import MCPAdapter

ROOT = Path(__file__).resolve().parents[1]


class Request(BaseModel):
    value: str


class Result(BaseModel):
    value: str


def app() -> App:
    value = App("runtime")

    @value.operation("values.echo")
    def echo(request: Request) -> Result:
        return Result(value=request.value)

    return value


def test_adapter_exposes_native_server_and_streamable_http_app() -> None:
    adapter = MCPAdapter(app())

    assert adapter.server is not None
    application = adapter.streamable_http_app(stateless_http=True, json_response=True)

    assert isinstance(application, Starlette)
    assert any(getattr(route, "path", None) == "/mcp" for route in application.routes)


def test_stdio_runner_is_an_async_entry_point() -> None:
    adapter = MCPAdapter(app())

    assert callable(adapter.run_stdio)


@pytest.mark.asyncio
async def test_stdio_server_lists_and_calls_a_tool_over_protocol_streams() -> None:
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "tests" / "fixtures" / "mcp_stdio_server.py")],
        cwd=ROOT,
    )

    async with Client(stdio_client(server), raise_exceptions=True, mode="legacy") as client:
        page = await client.list_tools()
        result = await client.call_tool("messages.echo", {"text": "hello over stdio"})

    assert [tool.name for tool in page.tools] == ["messages.echo"]
    assert result.is_error is False
    assert result.structured_content["result"] == {"message": "hello over stdio"}
