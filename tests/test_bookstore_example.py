import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from click.testing import CliRunner
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent_surface import OperationError
from examples.bookstore import (
    Bookstore,
    CancelHoldRequest,
    CreateHoldRequest,
    DeleteHoldRequest,
    SearchRequest,
    build_surface,
)

ROOT = Path(__file__).resolve().parents[1]


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
    assert actions["get"]["description"] == "Read this hold"
    assert actions["cancel"]["description"] == "Cancel this hold"
    assert actions["delete"]["description"] == "Delete this hold"


@pytest.mark.asyncio
async def test_book_availability_and_reserve_action_follow_persisted_hold_state(tmp_path) -> None:
    surface = build_surface(db_path=tmp_path / "bookstore.sqlite3")

    before = await surface.app.invoke("books.inspect", {"book": {"value": "book_dune"}})
    before_actions = surface.actions.actions_for(operation="books.inspect", result=before)
    created = await surface.app.invoke(
        "holds.create", {"book": {"value": "book_dune"}, "confirm": True}
    )
    active = await surface.app.invoke("books.inspect", {"book": {"value": "book_dune"}})
    active_actions = surface.actions.actions_for(operation="books.inspect", result=active)
    await surface.app.invoke(
        "holds.cancel", {"hold": created.id, "confirm": True}
    )
    cancelled = await surface.app.invoke("books.inspect", {"book": {"value": "book_dune"}})
    cancelled_actions = surface.actions.actions_for(
        operation="books.inspect", result=cancelled
    )
    await surface.app.invoke("holds.delete", {"hold": created.id, "confirm": True})
    deleted = await surface.app.invoke("books.inspect", {"book": {"value": "book_dune"}})
    deleted_actions = surface.actions.actions_for(operation="books.inspect", result=deleted)

    assert before.available is True
    assert [action.rel for action in before_actions.items] == ["reserve"]
    assert active.available is False
    assert active_actions.items == ()
    assert cancelled.available is False
    assert cancelled_actions.items == ()
    assert deleted.available is True
    assert [action.rel for action in deleted_actions.items] == ["reserve"]


def test_delete_is_atomic_across_two_connections(tmp_path, monkeypatch) -> None:
    database = tmp_path / "bookstore.sqlite3"
    surface = build_surface(db_path=database)
    surface.store.create_hold(
        CreateHoldRequest(book={"value": "book_dune"}, confirm=True)
    )
    original_get = Bookstore.get_hold
    reads = Barrier(2)

    def synchronized_get(store, request):
        hold = original_get(store, request)
        reads.wait(timeout=5)
        return hold

    monkeypatch.setattr(Bookstore, "get_hold", synchronized_get)

    def delete() -> str:
        store = Bookstore(database)
        try:
            store.delete_hold(DeleteHoldRequest(hold="hold_book_dune", confirm=True))
        except OperationError as error:
            return error.code
        return "deleted"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: delete(), range(2)))

    assert sorted(outcomes) == ["deleted", "hold_not_found"]


def test_cancel_is_one_atomic_statement(tmp_path, monkeypatch) -> None:
    store = Bookstore(tmp_path / "bookstore.sqlite3")
    store.create_hold(CreateHoldRequest(book={"value": "book_dune"}, confirm=True))

    def unexpected_read(*args, **kwargs):
        raise AssertionError("cancel must not read before updating")

    monkeypatch.setattr(store, "get_hold", unexpected_read)

    cancelled = store.cancel_hold(
        CancelHoldRequest(hold="hold_book_dune", confirm=True)
    )
    assert cancelled.status == "cancelled"


@pytest.mark.asyncio
async def test_bookstore_stdio_process_runs_persistent_crud(tmp_path) -> None:
    server = StdioServerParameters(
        command=str(ROOT / "examples" / "bookstore-mcp"),
        env={"AGENT_SURFACE_BOOKSTORE_DB": str(tmp_path / "bookstore.sqlite3")},
        cwd=ROOT,
    )

    async with Client(stdio_client(server), raise_exceptions=True, mode="legacy") as client:
        tools = await client.list_tools()
        created = await client.call_tool(
            "holds.create", {"book": "book_dune", "confirm": True}
        )
        found = await client.call_tool(
            "holds.get", {"hold": created.structured_content["result"]["id"]}
        )
        cancelled = await client.call_tool(
            "holds.cancel", {"hold": "hold_book_dune", "confirm": True}
        )
        deleted = await client.call_tool(
            "holds.delete", {"hold": "hold_book_dune", "confirm": True}
        )
        missing = await client.call_tool("holds.get", {"hold": "hold_book_dune"})

    assert {tool.name for tool in tools.tools} >= {
        "holds.create",
        "holds.get",
        "holds.cancel",
        "holds.delete",
    }
    assert created.structured_content["result"] == found.structured_content["result"]
    assert cancelled.structured_content["result"]["status"] == "cancelled"
    assert deleted.structured_content["result"]["id"] == "hold_book_dune"
    assert missing.structured_content["error"]["code"] == "hold_not_found"
