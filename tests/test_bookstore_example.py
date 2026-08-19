import asyncio
import json

import pytest
from click.testing import CliRunner
from mcp import Client

from examples.bookstore import SearchRequest, build_surface


def invoke(command, argv: list[str]):
    result = CliRunner().invoke(command, [*argv, "--format", "json"])
    return result, json.loads(result.stdout)


def test_bookstore_domain_runs_directly_from_the_shared_registry() -> None:
    surface = build_surface()

    page = asyncio.run(
        surface.app.invoke("books.search", SearchRequest(query="dune", limit=2))
    )

    assert [book.ref.value for book in page.items] == ["book_dune", "book_dune_messiah"]
    assert page.truncated is True
    assert page.next_cursor == "book_dune_messiah"


def test_bookstore_cli_follows_returned_actions_through_state() -> None:
    surface = build_surface()
    command = surface.cli()

    searched, search_document = invoke(
        command,
        ["books", "search", "--query", "dune", "--limit", "2"],
    )
    inspect_action = next(
        action for action in search_document["next_actions"]["items"] if action["rel"] == "inspect"
    )
    inspected, inspect_document = invoke(command, inspect_action["command"][1:])
    reserve_action = next(
        action
        for action in inspect_document["next_actions"]["items"]
        if action["rel"] == "reserve"
    )
    reserved, reserve_document = invoke(command, reserve_action["command"][1:])

    assert searched.exit_code == inspected.exit_code == reserved.exit_code == 0
    assert search_document["result"]["returned"] == 2
    assert inspect_document["result"]["title"] == "Dune"
    assert reserve_document["result"]["status"] == "active"
    assert reserve_document["result"]["book"] == {"value": "book_dune"}


def test_bookstore_domain_is_transport_independent() -> None:
    surface = build_surface()

    assert surface.store.__class__.__module__ == "examples.bookstore"


@pytest.mark.asyncio
async def test_bookstore_mcp_follows_operation_and_bound_values_through_state() -> None:
    surface = build_surface()

    async with Client(surface.mcp().server, raise_exceptions=True) as client:
        searched = await client.call_tool("books.search", {"query": "dune", "limit": 2})
        inspect_action = next(
            action
            for action in searched.structured_content["next_actions"]["items"]
            if action["rel"] == "inspect"
        )
        inspected = await client.call_tool(
            inspect_action["operation"], inspect_action["bound"]
        )
        reserve_action = next(
            action
            for action in inspected.structured_content["next_actions"]["items"]
            if action["rel"] == "reserve"
        )
        reserved = await client.call_tool(
            reserve_action["operation"], reserve_action["bound"]
        )

    assert searched.structured_content["result"]["returned"] == 2
    assert inspected.structured_content["result"]["title"] == "Dune"
    assert reserved.structured_content["result"] == {
        "id": "hold_book_dune",
        "book": {"value": "book_dune"},
        "status": "active",
    }
