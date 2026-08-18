import json
from dataclasses import dataclass

from click.testing import CliRunner
from pydantic import BaseModel, Field

from agent_surface import (
    ActionCollection,
    App,
    OperationError,
    OutputBudget,
    ReferenceRegistry,
    RenderOptions,
)
from agent_surface.adapters.click import ClickAdapter


class EchoRequest(BaseModel):
    text: str
    count: int = Field(default=1, ge=1, le=3)
    access_token: str = Field(default="safe", json_schema_extra={"sensitive": True})


class EchoResult(BaseModel):
    message: str


def echo_app() -> App:
    app = App("echo", version="1.0.0")

    @app.operation("message.echo", summary="Echo a message", read_only=True)
    def echo(request: EchoRequest) -> EchoResult:
        if request.text == "missing":
            raise OperationError(
                "message_missing",
                "Message was not found",
                details=({"text": request.text},),
                fix="Choose another message.",
            )
        if request.text == "explode":
            raise RuntimeError("private traceback detail")
        return EchoResult(message=request.text * request.count)

    return app


def invoke_json(app: App, args: list[str], **adapter_options: object):
    command = ClickAdapter(app, **adapter_options).command()  # type: ignore[arg-type]
    result = CliRunner().invoke(command, [*args, "--format", "json"])
    return result, json.loads(result.stdout)


def test_sync_invocation_emits_result_and_preserves_raw_argv_boundaries() -> None:
    result, document = invoke_json(
        echo_app(),
        ["message", "echo", "--text", "hello world", "--count", "2"],
    )

    assert result.exit_code == 0
    assert document["result"] == {"message": "hello worldhello world"}
    assert document["command"]["raw"] == [
        "echo",
        "message",
        "echo",
        "--text",
        "hello world",
        "--count",
        "2",
        "--format",
        "json",
    ]
    assert document["command"]["parsed"]["path"] == ["message", "echo"]
    assert document["command"]["parsed"]["options"]["count"] == 2


def test_default_rendering_is_yaml_with_small_flow_collections() -> None:
    command = ClickAdapter(echo_app()).command()

    result = CliRunner().invoke(command, ["message", "echo", "--text", "hello"])

    assert result.exit_code == 0
    assert "ok: true" in result.stdout
    assert "result: {message: hello}" in result.stdout


def test_async_handler_uses_the_same_registry_invocation_path() -> None:
    class Request(BaseModel):
        value: int

    class Result(BaseModel):
        doubled: int

    app = App("async-app")

    @app.operation("number.double")
    async def double(request: Request) -> Result:
        return Result(doubled=request.value * 2)

    result, document = invoke_json(app, ["number", "double", "--value", "3"])

    assert result.exit_code == 0
    assert document["result"] == {"doubled": 6}


def test_reference_token_decodes_before_pydantic_validation() -> None:
    @dataclass(frozen=True)
    class BookRef:
        value: str

    class BookCodec:
        kind = "book"
        python_type = BookRef

        def encode(self, value: BookRef) -> str:
            return value.value

        def decode(self, token: str) -> BookRef:
            return BookRef(value=token)

        def display(self, value: BookRef) -> str:
            return value.value

    class Request(BaseModel):
        book: BookRef

    class Result(BaseModel):
        book: str

    app = App("books")

    @app.operation("books.inspect")
    def inspect(request: Request) -> Result:
        return Result(book=request.book.value)

    references = ReferenceRegistry()
    references.register(BookCodec())

    result, document = invoke_json(
        app,
        ["books", "inspect", "--book", "book_dune"],
        references=references,
    )

    assert result.exit_code == 0
    assert document["result"] == {"book": "book_dune"}


def test_input_and_domain_errors_are_structured_with_stable_exits() -> None:
    invalid, invalid_document = invoke_json(
        echo_app(),
        ["message", "echo", "--text", "hello", "--count", "9"],
    )
    missing, missing_document = invoke_json(
        echo_app(),
        ["message", "echo", "--text", "missing"],
    )

    assert invalid.exit_code == 2
    assert invalid_document["error"]["code"] == "invalid_input"
    assert missing.exit_code == 4
    assert missing_document["error"]["code"] == "message_missing"
    assert missing_document["fix"] == "Choose another message."


def test_click_parse_error_is_a_repairable_structured_document() -> None:
    result, document = invoke_json(echo_app(), ["message", "echo"])

    assert result.exit_code == 2
    assert document["error"]["code"] == "missing_parameter"
    assert document["command"]["raw"] == [
        "echo",
        "message",
        "echo",
        "--format",
        "json",
    ]
    assert document["fix"]


def test_unknown_nested_command_is_a_repairable_structured_document() -> None:
    command = ClickAdapter(echo_app()).command()

    result = CliRunner().invoke(command, ["message", "missing", "--format", "json"])
    document = json.loads(result.stdout)

    assert result.exit_code == 2
    assert document["error"]["code"] == "unknown_command"
    assert document["command"]["raw"] == [
        "echo",
        "message",
        "missing",
        "--format",
        "json",
    ]
    assert document["fix"]


def test_unexpected_failure_is_structured_without_private_details() -> None:
    result, document = invoke_json(
        echo_app(),
        ["message", "echo", "--text", "explode"],
    )

    assert result.exit_code == 70
    assert document["error"]["code"] == "internal_error"
    assert "private traceback detail" not in result.output


def test_oversized_success_becomes_a_structured_size_error() -> None:
    options = RenderOptions(budget=OutputBudget(max_bytes=1_024))

    result, document = invoke_json(
        echo_app(),
        ["message", "echo", "--text", "x" * 2_000],
        render_options=options,
    )

    assert result.exit_code == 70
    assert document["error"]["code"] == "response_too_large"


def test_sensitive_values_are_redacted_from_every_output_view() -> None:
    result, document = invoke_json(
        echo_app(),
        [
            "message",
            "echo",
            "--text",
            "hello",
            "--access-token",
            "consumer-secret",
        ],
    )

    assert result.exit_code == 0
    assert "consumer-secret" not in result.output
    assert "<redacted>" in document["command"]["raw"]
    assert document["command"]["parsed"]["options"]["access_token"] == "<redacted>"


def test_destructive_operation_requires_confirmation_before_handler_runs() -> None:
    class Request(BaseModel):
        item: str
        confirm: bool = False

    class Result(BaseModel):
        changed: bool

    calls = 0
    app = App("inventory")

    @app.operation("items.delete", destructive=True)
    def delete(request: Request) -> Result:
        nonlocal calls
        calls += 1
        return Result(changed=request.confirm)

    denied, denied_document = invoke_json(app, ["items", "delete", "--item", "one"])
    allowed, allowed_document = invoke_json(
        app,
        ["items", "delete", "--item", "one", "--confirm"],
    )

    assert denied.exit_code == 3
    assert denied_document["error"]["code"] == "confirmation_required"
    assert allowed.exit_code == 0
    assert allowed_document["result"] == {"changed": True}
    assert calls == 1


def test_error_action_provider_receives_the_invoked_operation() -> None:
    class RecordingActions:
        def __init__(self) -> None:
            self.operations: list[str] = []

        def actions_for(
            self,
            *,
            operation: str,
            result: object | None = None,
            error: OperationError | None = None,
        ) -> ActionCollection:
            if error is not None:
                self.operations.append(operation)
            return ActionCollection()

        def list_actions(
            self,
            *,
            cursor: str | None = None,
            budget: OutputBudget | None = None,
        ) -> ActionCollection:
            return ActionCollection()

        def explain(self, operation: str):
            return None

    actions = RecordingActions()

    result, _ = invoke_json(
        echo_app(),
        ["message", "echo", "--text", "missing"],
        action_provider=actions,
    )

    assert result.exit_code == 4
    assert actions.operations == ["message.echo"]
