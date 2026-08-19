import asyncio
import json
from typing import Any

import pytest
from click.testing import CliRunner
from mcp import Client

from agent_surface import OperationError
from agent_surface.adapters.click import ClickAdapter
from tests.reference_consumer import integration


def invoke_click(args: list[str]) -> dict[str, Any]:
    app, _catalog = integration.build_app()
    command = ClickAdapter(app, references=integration.build_references()).command()
    result = CliRunner().invoke(command, [*args, "--format", "json"])
    return json.loads(result.stdout)


@pytest.mark.asyncio
async def test_lookup_has_equivalent_direct_click_and_mcp_results() -> None:
    app, _catalog = integration.build_app()
    direct = await app.invoke("resource.lookup", {"ref": {"value": "resource-a"}})
    click = await asyncio.to_thread(
        invoke_click, ["resource", "lookup", "--ref", "resource-a"]
    )
    adapter, _catalog = integration.build_mcp_adapter()

    async with Client(adapter.server, raise_exceptions=True) as client:
        mcp = await client.call_tool("resource.lookup", {"ref": "resource-a"})

    assert direct.model_dump(mode="json") == click["result"] == mcp.structured_content["result"]


@pytest.mark.asyncio
async def test_async_page_has_equivalent_direct_click_and_mcp_results() -> None:
    app, _catalog = integration.build_app()
    direct = await app.invoke("resource.list", {"limit": 1})
    click = await asyncio.to_thread(invoke_click, ["resource", "list", "--limit", "1"])
    adapter, _catalog = integration.build_mcp_adapter()

    async with Client(adapter.server, raise_exceptions=True) as client:
        mcp = await client.call_tool("resource.list", {"limit": 1})

    assert direct.model_dump(mode="json") == click["result"] == mcp.structured_content["result"]


@pytest.mark.asyncio
async def test_domain_error_has_equivalent_direct_click_and_mcp_semantics() -> None:
    app, _catalog = integration.build_app()
    with pytest.raises(OperationError) as direct:
        await app.invoke("resource.lookup", {"ref": {"value": "missing"}})
    click = await asyncio.to_thread(
        invoke_click, ["resource", "lookup", "--ref", "missing"]
    )
    adapter, _catalog = integration.build_mcp_adapter()

    async with Client(adapter.server, raise_exceptions=True) as client:
        mcp = await client.call_tool("resource.lookup", {"ref": "missing"})

    assert direct.value.code == click["error"]["code"] == mcp.structured_content["error"]["code"]
    assert direct.value.fix == click["fix"] == mcp.structured_content["fix"]


@pytest.mark.asyncio
async def test_confirmed_mutation_has_equivalent_direct_click_and_mcp_results() -> None:
    payload = {
        "ref": {"value": "resource-a"},
        "confirm": True,
        "access_token": "consumer-secret",
    }
    app, _catalog = integration.build_app()
    direct = await app.invoke("resource.mutate", payload)
    click = await asyncio.to_thread(
        invoke_click,
        [
            "resource",
            "mutate",
            "--ref",
            "resource-a",
            "--access-token",
            "consumer-secret",
            "--confirm",
        ],
    )
    adapter, _catalog = integration.build_mcp_adapter()

    async with Client(adapter.server, raise_exceptions=True) as client:
        mcp = await client.call_tool(
            "resource.mutate",
            {
                "ref": "resource-a",
                "confirm": True,
                "access_token": "consumer-secret",
            },
        )

    assert direct.model_dump(mode="json") == click["result"] == mcp.structured_content["result"]
    assert "consumer-secret" not in mcp.content[0].text
