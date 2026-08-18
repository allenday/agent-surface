from pydantic import BaseModel
from starlette.applications import Starlette

from agent_surface import App
from agent_surface.adapters.mcp import MCPAdapter


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
