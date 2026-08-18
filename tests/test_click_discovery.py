import json

from click.testing import CliRunner
from pydantic import BaseModel

from agent_surface import Action, ActionCatalog, ActionCollection, App, OutputBudget
from agent_surface.adapters.click import ClickAdapter


class Request(BaseModel):
    value: str = "default"


class Result(BaseModel):
    status: str


def app_with_operations(count: int = 3) -> App:
    app = App("catalog")
    for index in range(count):
        def make_handler(operation_index: int):
            def handler(request: Request) -> Result:
                return Result(status=f"{operation_index}:{request.value}")

            return handler

        app.operations.register(
            f"items.operation-{index:03d}",
            make_handler(index),
            summary=f"Operation {index}",
            read_only=True,
        )
    return app


def invoke_json(command, args: list[str]):
    result = CliRunner().invoke(command, [*args, "--format", "json"])
    return result, json.loads(result.stdout)


def test_operations_list_is_bounded_and_every_page_is_reachable() -> None:
    command = ClickAdapter(app_with_operations(45)).command()
    cursor = None
    names: list[str] = []

    while True:
        args = ["operations", "list", "--limit", "20"]
        if cursor is not None:
            args.extend(("--cursor", cursor))
        result, document = invoke_json(command, args)

        assert result.exit_code == 0
        page = document["result"]
        assert page["returned"] <= 20
        assert page["total"] == 45
        names.extend(item["name"] for item in page["items"])
        if not page["truncated"]:
            assert "continuation" not in page
            break
        continuation = page["continuation"]["command"]
        assert continuation[:3] == ["catalog", "operations", "list"]
        cursor = continuation[continuation.index("--cursor") + 1]

    assert names == [f"items.operation-{index:03d}" for index in range(45)]


def test_operations_describe_returns_pydantic_schemas() -> None:
    command = ClickAdapter(app_with_operations()).command()

    result, document = invoke_json(
        command,
        ["operations", "describe", "items.operation-001"],
    )

    assert result.exit_code == 0
    assert document["result"]["name"] == "items.operation-001"
    assert document["result"]["input_schema"]["properties"]["value"]["type"] == "string"
    assert document["result"]["output_schema"]["properties"]["status"]["type"] == "string"


class StaticActions:
    def __init__(self) -> None:
        self._catalog = ActionCatalog(
            (
                Action(
                    rel="inspect",
                    operation="items.operation-000",
                    command=("catalog", "items", "operation-000"),
                ),
            ),
            discovery_command=("catalog", "actions", "list"),
        )

    def actions_for(
        self,
        *,
        operation: str,
        result: object | None = None,
        error: object | None = None,
    ) -> ActionCollection:
        return ActionCollection()

    def list_actions(
        self,
        *,
        cursor: str | None = None,
        budget: OutputBudget | None = None,
    ) -> ActionCollection:
        return self._catalog.page(cursor=cursor, budget=budget)

    def explain(self, operation: str) -> Action | None:
        page = self._catalog.page()
        return next((item for item in page.items if item.operation == operation), None)


def test_actions_list_and_explain_use_the_explicit_provider() -> None:
    command = ClickAdapter(
        app_with_operations(),
        action_provider=StaticActions(),  # type: ignore[arg-type]
    ).command()

    listed, list_document = invoke_json(command, ["actions", "list"])
    explained, explain_document = invoke_json(
        command,
        ["actions", "explain", "items.operation-000"],
    )

    assert listed.exit_code == 0
    assert list_document["result"]["returned"] == 1
    assert explained.exit_code == 0
    assert explain_document["result"]["rel"] == "inspect"


def test_invalid_operation_cursor_is_a_structured_error() -> None:
    command = ClickAdapter(app_with_operations()).command()

    result, document = invoke_json(
        command,
        ["operations", "list", "--cursor", "not-a-cursor"],
    )

    assert result.exit_code == 2
    assert document["error"]["code"] == "invalid_operation_cursor"


def test_discovery_yaml_never_uses_ellipsis_placeholders() -> None:
    command = ClickAdapter(app_with_operations(25)).command()

    result = CliRunner().invoke(command, ["operations", "list"])

    assert result.exit_code == 0
    assert "..." not in result.stdout


def test_discovery_missing_parameter_is_a_structured_error() -> None:
    command = ClickAdapter(app_with_operations()).command()

    result, document = invoke_json(command, ["operations", "describe"])

    assert result.exit_code == 2
    assert document["error"]["code"] == "missing_parameter"
    assert document["command"]["parsed"]["path"] == ["operations", "describe"]


def test_unknown_discovery_command_is_a_structured_error() -> None:
    command = ClickAdapter(app_with_operations()).command()

    result, document = invoke_json(command, ["operations", "missing"])

    assert result.exit_code == 2
    assert document["error"]["code"] == "unknown_command"
    assert document["command"]["parsed"]["path"] == ["operations"]
