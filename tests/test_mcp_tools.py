import pytest
from mcp import Client
from pydantic import BaseModel, Field

from agent_surface import App
from agent_surface.adapters.mcp import MCPAdapter


class SearchRequest(BaseModel):
    query: str = Field(min_length=2)


class SearchResult(BaseModel):
    count: int


def catalog_app(count: int = 1) -> App:
    app = App("catalog", version="1.0")
    for index in range(count):
        def make_handler(operation_index: int):
            def handler(request: SearchRequest) -> SearchResult:
                return SearchResult(count=operation_index + len(request.query))

            return handler

        app.operations.register(
            f"books.search-{index:03d}",
            make_handler(index),
            summary=f"Search operation {index}",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        )
    return app


@pytest.mark.asyncio
async def test_native_tools_preserve_names_schemas_and_annotations() -> None:
    adapter = MCPAdapter(catalog_app())

    async with Client(adapter.server, raise_exceptions=True) as client:
        page = await client.list_tools()

    assert [tool.name for tool in page.tools] == ["books.search-000"]
    tool = page.tools[0]
    assert tool.description == "Search operation 0"
    assert tool.input_schema["properties"]["query"]["minLength"] == 2
    assert tool.output_schema is not None
    assert tool.output_schema["properties"]["ok"]["const"] is True
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.destructive_hint is False
    assert tool.annotations.idempotent_hint is True
    assert tool.annotations.open_world_hint is False


@pytest.mark.asyncio
async def test_stdin_cli_metadata_does_not_change_the_mcp_input_schema() -> None:
    class BootstrapRequest(BaseModel):
        bws_token: str = Field(
            min_length=1,
            json_schema_extra={"sensitive": True, "cli": {"source": "stdin"}},
        )

    app = App("bootstrap")

    @app.operation("host.bootstrap")
    def bootstrap(request: BootstrapRequest) -> SearchResult:
        return SearchResult(count=len(request.bws_token))

    async with Client(MCPAdapter(app).server, raise_exceptions=True) as client:
        page = await client.list_tools()
        result = await client.call_tool("host.bootstrap", {"bws_token": "consumer-secret"})

    assert page.tools[0].input_schema["properties"]["bws_token"]["minLength"] == 1
    assert result.structured_content["result"] == {"count": 15}


@pytest.mark.asyncio
async def test_tool_discovery_is_deterministic_and_cursor_paginated() -> None:
    adapter = MCPAdapter(catalog_app(400), page_size=20)
    names: list[str] = []
    cursor = None

    async with Client(adapter.server, raise_exceptions=True) as client:
        while True:
            page = await client.list_tools(cursor=cursor)
            assert len(page.tools) <= 20
            names.extend(tool.name for tool in page.tools)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor

    assert names == [f"books.search-{index:03d}" for index in range(400)]


@pytest.mark.asyncio
async def test_malformed_tool_cursor_is_rejected() -> None:
    adapter = MCPAdapter(catalog_app(3), page_size=2)

    async with Client(adapter.server, raise_exceptions=True) as client:
        with pytest.raises(Exception, match="cursor"):
            await client.list_tools(cursor="not-a-cursor")
