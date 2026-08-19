import asyncio

from pydantic import BaseModel

from agent_surface import App
from agent_surface.adapters.mcp import MCPAdapter


class EchoRequest(BaseModel):
    text: str


class EchoResult(BaseModel):
    message: str


def build_app() -> App:
    app = App("stdio-fixture", version="1.0")

    @app.operation("messages.echo", read_only=True, idempotent=True)
    def echo(request: EchoRequest) -> EchoResult:
        return EchoResult(message=request.text)

    return app


if __name__ == "__main__":
    asyncio.run(MCPAdapter(build_app()).run_stdio())
