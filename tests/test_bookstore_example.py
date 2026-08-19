import asyncio
import json

import pytest
from click.testing import CliRunner
from mcp import Client

from agent_surface import OperationError
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


@pytest.mark.asyncio
async def test_sqlite_hold_persists_across_surface_instances(tmp_path) -> None:
    database = tmp_path / "bookstore.sqlite3"
    first = build_surface(db_path=database)

    created = await first.app.invoke(
        "holds.create", {"book": {"value": "book_dune"}, "confirm": True}
    )
    second = build_surface(db_path=database)
    found = await second.app.invoke("holds.get", {"hold": created.id})

    assert found == created


@pytest.mark.asyncio
async def test_sqlite_hold_create_rejects_a_duplicate(tmp_path) -> None:
    surface = build_surface(db_path=tmp_path / "bookstore.sqlite3")
    payload = {"book": {"value": "book_dune"}, "confirm": True}
    await surface.app.invoke("holds.create", payload)

    with pytest.raises(OperationError) as duplicate:
        await surface.app.invoke("holds.create", payload)

    assert duplicate.value.code == "hold_exists"


@pytest.mark.asyncio
async def test_sqlite_hold_cancel_persists_as_an_update(tmp_path) -> None:
    database = tmp_path / "bookstore.sqlite3"
    surface = build_surface(db_path=database)
    created = await surface.app.invoke(
        "holds.create", {"book": {"value": "book_dune"}, "confirm": True}
    )

    cancelled = await surface.app.invoke(
        "holds.cancel", {"hold": created.id, "confirm": True}
    )
    found = await build_surface(db_path=database).app.invoke(
        "holds.get", {"hold": created.id}
    )

    assert cancelled.status == found.status == "cancelled"


@pytest.mark.asyncio
async def test_sqlite_hold_delete_removes_the_record(tmp_path) -> None:
    database = tmp_path / "bookstore.sqlite3"
    surface = build_surface(db_path=database)
    created = await surface.app.invoke(
        "holds.create", {"book": {"value": "book_dune"}, "confirm": True}
    )

    deleted = await surface.app.invoke(
        "holds.delete", {"hold": created.id, "confirm": True}
    )

    assert deleted == created
    with pytest.raises(OperationError) as missing:
        await build_surface(db_path=database).app.invoke(
            "holds.get", {"hold": created.id}
        )
    assert missing.value.code == "hold_not_found"


@pytest.mark.asyncio
async def test_created_hold_advertises_concrete_read_update_delete_actions(tmp_path) -> None:
    surface = build_surface(db_path=tmp_path / "bookstore.sqlite3")

    async with Client(surface.mcp().server, raise_exceptions=True) as client:
        created = await client.call_tool(
            "holds.create", {"book": "book_dune", "confirm": True}
        )

    actions = {
        item["rel"]: item
        for item in created.structured_content["next_actions"]["items"]
    }
    assert actions["get"]["bound"] == {"hold": "hold_book_dune"}
    assert actions["cancel"]["bound"] == {
        "hold": "hold_book_dune",
        "confirm": True,
    }
    assert actions["delete"]["bound"] == {
        "hold": "hold_book_dune",
        "confirm": True,
    }
