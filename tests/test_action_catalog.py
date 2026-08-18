from ruamel.yaml import YAML

from agent_surface import (
    Action,
    CommandView,
    OutputBudget,
    ParsedCommand,
    RenderOptions,
    SuccessEnvelope,
    render_envelope,
)
from agent_surface.actions import ActionCatalog, InvalidActionCursor


def actions(count: int) -> tuple[Action, ...]:
    return tuple(
        Action(
            rel="inspect-resource",
            operation="resource.inspect",
            command=("resource", "inspect", f"resource-{index:03d}"),
        )
        for index in range(count)
    )


def next_cursor(page) -> str:
    assert page.discover is not None
    assert page.discover.command is not None
    command = page.discover.command
    return command[command.index("--cursor") + 1]


def test_catalog_returns_one_bounded_page_and_immediate_continuation() -> None:
    catalog = ActionCatalog(actions(5))

    page = catalog.page(budget=OutputBudget(max_items=2))

    assert page.total == 5
    assert page.returned == 2
    assert page.truncated is True
    assert [item.command[-1] for item in page.items if item.command] == [
        "resource-000",
        "resource-001",
    ]
    assert page.discover is not None
    assert page.discover.rel == "next-page"
    assert page.discover.command[:2] == ("actions", "list")
    assert page.discover.command.count("--cursor") == 1


def test_catalog_cursor_reaches_each_action_exactly_once() -> None:
    catalog = ActionCatalog(actions(400))
    budget = OutputBudget(max_items=20)
    cursor = None
    found: list[str] = []

    while True:
        page = catalog.page(cursor=cursor, budget=budget)
        assert page.returned <= 20
        found.extend(item.command[-1] for item in page.items if item.command)
        if not page.truncated:
            assert page.discover is None
            break
        cursor = next_cursor(page)

    assert len(found) == 400
    assert len(set(found)) == 400
    assert set(found) == {f"resource-{index:03d}" for index in range(400)}


def test_catalog_rejects_malformed_wrong_version_and_out_of_range_cursors() -> None:
    catalog = ActionCatalog(actions(3))

    for cursor in ("not-a-cursor", "djI6MQ", "djE6OTk"):
        try:
            catalog.page(cursor=cursor, budget=OutputBudget(max_items=1))
        except InvalidActionCursor as error:
            assert error.code == "invalid_action_cursor"
        else:
            raise AssertionError(f"cursor should be invalid: {cursor}")


def test_high_branch_page_fits_default_byte_budget_and_round_trips() -> None:
    page = ActionCatalog(actions(400)).page()
    envelope = SuccessEnvelope[type(page)](
        command=CommandView(
            raw=("actions", "list"),
            parsed=ParsedCommand(path=("actions", "list")),
        ),
        result=page,
    )

    document = render_envelope(envelope, options=RenderOptions())
    parsed = YAML(typ="safe").load(document)

    assert len(document.encode("utf-8")) <= 65_536
    assert parsed["ok"] is True
    assert parsed["result"]["returned"] == 20
    assert parsed["result"]["total"] == 400
    assert "..." not in document
