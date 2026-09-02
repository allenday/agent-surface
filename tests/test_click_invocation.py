import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from click.testing import CliRunner
from pydantic import BaseModel, Field, create_model

from agent_surface import (
    ActionCollection,
    App,
    OperationError,
    OperationOutcome,
    OutputBudget,
    ReferenceRegistry,
    RenderOptions,
)
from agent_surface.adapters.click import ClickAdapter, CliDefinitionError


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


def test_declarative_boolean_option_aliases_bind_the_pydantic_field() -> None:
    class Request(BaseModel):
        apply_changes: bool = Field(
            default=False,
            json_schema_extra={"cli": {"options": ["--apply", "--apply-changes"]}},
        )

    class Result(BaseModel):
        applied: bool

    app = App("changes")

    @app.operation("changes.apply")
    def apply(request: Request) -> Result:
        return Result(applied=request.apply_changes)

    for option in ("--apply", "--apply-changes"):
        result, document = invoke_json(app, ["changes", "apply", option])

        assert result.exit_code == 0
        assert document["result"] == {"applied": True}


def test_sensitive_declarative_option_alias_is_redacted_from_raw_argv() -> None:
    class Request(BaseModel):
        api_token: str = Field(
            json_schema_extra={
                "sensitive": True,
                "cli": {"options": ["--token", "--api-token"]},
            }
        )

    class Result(BaseModel):
        accepted: bool

    app = App("tokens")

    @app.operation("tokens.use")
    def use(request: Request) -> Result:
        return Result(accepted=bool(request.api_token))

    result, document = invoke_json(
        app,
        ["tokens", "use", "--api-token", "secret-value"],
    )

    assert result.exit_code == 0
    assert "--api-token" in document["command"]["raw"]
    assert "<redacted>" in document["command"]["raw"]
    assert "secret-value" not in result.stdout


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


def test_successful_negative_outcome_renders_normally_with_its_exit_code() -> None:
    app = App("status")

    @app.operation("operation.status")
    def status(request: EchoRequest) -> OperationOutcome[EchoResult]:
        return OperationOutcome(EchoResult(message=request.text), exit_code=1)

    result, document = invoke_json(app, ["operation", "status", "--text", "failed"])

    assert result.exit_code == 1
    assert document["ok"] is True
    assert document["result"] == {"message": "failed"}


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
    assert invalid_document["error"]["code"] == "usage_error"
    assert missing.exit_code == 4
    assert missing_document["error"]["code"] == "message_missing"
    assert missing_document["fix"] == "Choose another message."


def test_shared_inputs_are_root_options_and_merge_into_the_operation_request() -> None:
    class SharedInputs(BaseModel):
        registry: str

    class Request(SharedInputs):
        host: str

    class Result(BaseModel):
        registry: str
        host: str

    app = App("infra", shared_input_model=SharedInputs)

    @app.operation("host.status", read_only=True)
    def status(request: Request) -> Result:
        return Result(registry=request.registry, host=request.host)

    result, document = invoke_json(
        app,
        ["--registry", "/var/lib/infra", "host", "status", "--host", "node-1"],
    )

    assert result.exit_code == 0
    assert document["result"] == {"registry": "/var/lib/infra", "host": "node-1"}
    assert document["command"]["raw"][:3] == ["infra", "--registry", "/var/lib/infra"]
    assert document["command"]["parsed"]["options"] == {
        "registry": "/var/lib/infra",
        "host": "node-1",
    }


def test_operation_error_exit_policy_maps_typed_error_codes() -> None:
    result, document = invoke_json(
        echo_app(),
        ["message", "echo", "--text", "missing"],
        operation_error_exit_code=lambda code: 3 if code == "message_missing" else 4,
    )

    assert result.exit_code == 3
    assert document["error"]["code"] == "message_missing"


def test_click_parse_error_is_a_repairable_structured_document() -> None:
    result, document = invoke_json(echo_app(), ["message", "echo"])

    assert result.exit_code == 2
    assert document["error"]["code"] == "usage_error"
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
    assert document["error"]["code"] == "usage_error"
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


def test_click_adapter_rejects_budget_too_small_for_structured_errors() -> None:
    with pytest.raises(CliDefinitionError) as raised:
        ClickAdapter(
            echo_app(),
            render_options=RenderOptions(budget=OutputBudget(max_bytes=100)),
        )

    assert getattr(raised.value, "code", None) == "cli_budget_too_small"


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


def test_sensitive_positional_value_is_redacted_from_raw_argv() -> None:
    class Request(BaseModel):
        secret: str = Field(
            json_schema_extra={"sensitive": True, "cli": {"kind": "argument"}}
        )

    app = App("vault")

    @app.operation("secrets.check", read_only=True)
    def check(request: Request) -> EchoResult:
        return EchoResult(message="accepted")

    result, document = invoke_json(app, ["secrets", "check", "consumer-secret"])

    assert result.exit_code == 0
    assert "consumer-secret" not in result.output
    assert document["command"]["raw"][-3] == "<redacted>"


def stdin_app() -> App:
    class Request(BaseModel):
        host: str
        bws_token: str = Field(
            min_length=1,
            json_schema_extra={
                "sensitive": True,
                "cli": {"source": "stdin", "max_bytes": 64, "strip_trailing_newline": True},
            },
        )

    app = App("bootstrap")

    @app.operation("host.bootstrap")
    def bootstrap(request: Request) -> EchoResult:
        return EchoResult(message=f"bootstrapped {request.host}")

    return app


def invoke_stdin(args: list[str], *, input: str | bytes) -> tuple[object, dict[str, object]]:
    command = ClickAdapter(stdin_app()).command()
    result = CliRunner().invoke(command, [*args, "--format", "json"], input=input)
    return result, json.loads(result.stdout)


def test_sensitive_stdin_field_is_absent_from_argv_and_redacted_from_output() -> None:
    result, document = invoke_stdin(
        ["host", "bootstrap", "--host", "node-1", "--bws-token-stdin"],
        input="consumer-secret\n",
    )

    assert result.exit_code == 0
    assert document["result"] == {"message": "bootstrapped node-1"}
    assert "consumer-secret" not in result.output
    assert "--bws-token" not in document["command"]["raw"]
    assert document["command"]["parsed"]["flags"] == ["bws-token-stdin"]


@pytest.mark.parametrize(
    ("input", "code"),
    [
        ("", "stdin_missing"),
        ("\n", "stdin_empty"),
        ("first\nsecond\n", "stdin_multiple_values"),
        ("x" * 65, "stdin_too_large"),
    ],
)
def test_sensitive_stdin_field_rejects_invalid_single_value_input(
    input: str,
    code: str,
) -> None:
    result, document = invoke_stdin(
        ["host", "bootstrap", "--host", "node-1", "--bws-token-stdin"],
        input=input,
    )

    assert result.exit_code == 2
    assert document["error"]["code"] == code
    if value := input.strip():
        assert value not in result.output


def test_sensitive_stdin_field_rejects_non_utf8_input() -> None:
    result, document = invoke_stdin(
        ["host", "bootstrap", "--host", "node-1", "--bws-token-stdin"],
        input=b"\xff",
    )

    assert result.exit_code == 2
    assert document["error"]["code"] == "stdin_invalid_encoding"


def test_sensitive_bad_lexical_value_is_redacted_from_parse_error() -> None:
    class Request(BaseModel):
        pin: int = Field(json_schema_extra={"sensitive": True})

    app = App("vault")

    @app.operation("secrets.check", read_only=True)
    def check(request: Request) -> EchoResult:
        return EchoResult(message=str(request.pin))

    result, document = invoke_json(
        app,
        ["secrets", "check", "--pin", "not-a-secret-pin"],
    )

    assert result.exit_code == 2
    assert document["error"]["code"] == "usage_error"
    assert "not-a-secret-pin" not in result.output


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
            self.requests: list[BaseModel | None] = []

        def actions_for(
            self,
            *,
            operation: str,
            request: BaseModel | None = None,
            result: object | None = None,
            error: OperationError | None = None,
        ) -> ActionCollection:
            if error is not None:
                self.operations.append(operation)
                self.requests.append(request)
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
    assert actions.requests == [EchoRequest(text="missing")]


def test_action_provider_receives_validated_request_context() -> None:
    class ContextActions:
        def __init__(self) -> None:
            self.requests: list[BaseModel | None] = []

        def actions_for(
            self,
            *,
            operation: str,
            request: BaseModel | None = None,
            result: object | None = None,
            error: OperationError | None = None,
        ) -> ActionCollection:
            self.requests.append(request)
            return ActionCollection()

        def list_actions(self, **kwargs: object) -> ActionCollection:
            return ActionCollection()

        def explain(self, operation: str):
            return None

    actions = ContextActions()

    result, _ = invoke_json(
        echo_app(),
        ["message", "echo", "--text", "hello", "--count", "2"],
        action_provider=actions,
    )

    assert result.exit_code == 0
    assert actions.requests == [EchoRequest(text="hello", count=2)]


def test_legacy_action_provider_without_request_remains_supported() -> None:
    class LegacyActions:
        def __init__(self) -> None:
            self.operations: list[str] = []

        def actions_for(
            self,
            *,
            operation: str,
            result: object | None = None,
            error: OperationError | None = None,
        ) -> ActionCollection:
            self.operations.append(operation)
            return ActionCollection()

        def list_actions(self, **kwargs: object) -> ActionCollection:
            return ActionCollection()

        def explain(self, operation: str):
            return None

    actions = LegacyActions()

    result, document = invoke_json(
        echo_app(),
        ["message", "echo", "--text", "hello"],
        action_provider=actions,
    )

    assert result.exit_code == 0
    assert document["result"] == {"message": "hello"}
    assert actions.operations == ["message.echo"]


def test_action_provider_type_error_is_not_retried_as_a_legacy_provider() -> None:
    class BrokenActions:
        def __init__(self) -> None:
            self.calls: list[tuple[BaseModel | None, bool, bool]] = []

        def actions_for(
            self,
            *,
            operation: str,
            request: BaseModel | None = None,
            result: object | None = None,
            error: OperationError | None = None,
        ) -> ActionCollection:
            self.calls.append((request, result is not None, error is not None))
            if result is not None:
                raise TypeError("provider failed internally")
            return ActionCollection()

        def list_actions(self, **kwargs: object) -> ActionCollection:
            return ActionCollection()

        def explain(self, operation: str):
            return None

    actions = BrokenActions()

    result, document = invoke_json(
        echo_app(),
        ["message", "echo", "--text", "hello"],
        action_provider=actions,
    )

    assert result.exit_code == 70
    assert document["error"]["code"] == "internal_error"
    assert actions.calls == [
        (EchoRequest(text="hello"), True, False),
        (EchoRequest(text="hello"), False, True),
    ]


def test_action_provider_receives_no_request_for_validation_failure() -> None:
    class ContextActions:
        def __init__(self) -> None:
            self.requests: list[BaseModel | None] = []

        def actions_for(
            self,
            *,
            operation: str,
            request: BaseModel | None = None,
            result: object | None = None,
            error: OperationError | None = None,
        ) -> ActionCollection:
            self.requests.append(request)
            return ActionCollection()

        def list_actions(self, **kwargs: object) -> ActionCollection:
            return ActionCollection()

        def explain(self, operation: str):
            return None

    actions = ContextActions()

    result, _ = invoke_json(
        echo_app(),
        ["message", "echo", "--text", "hello", "--count", "9"],
        action_provider=actions,
    )

    assert result.exit_code == 2
    assert actions.requests == [None]


def test_reference_decode_failure_is_structured() -> None:
    @dataclass(frozen=True)
    class Ref:
        value: str

    class Codec:
        kind = "ref"
        python_type = Ref

        def encode(self, value: Ref) -> str:
            return value.value

        def decode(self, token: str) -> Ref:
            raise ValueError("unknown reference")

        def display(self, value: Ref) -> str:
            return value.value

    class Request(BaseModel):
        ref: Ref

    app = App("refs")

    @app.operation("refs.inspect")
    def inspect(request: Request) -> EchoResult:
        return EchoResult(message=request.ref.value)

    references = ReferenceRegistry()
    references.register(Codec())
    result, document = invoke_json(
        app, ["refs", "inspect", "--ref", "missing"], references=references
    )

    assert result.exit_code == 2
    assert document["error"]["code"] == "invalid_reference"


def test_oversized_error_still_emits_a_structured_fallback() -> None:
    class Request(BaseModel):
        text: str = Field(max_length=3)

    app = App("small")

    @app.operation("text.check")
    def check(request: Request) -> EchoResult:
        return EchoResult(message=request.text)

    options = RenderOptions(budget=OutputBudget(max_bytes=1_024))
    result, document = invoke_json(
        app,
        ["text", "check", "--text", "x" * 2_000],
        render_options=options,
    )

    assert result.exit_code == 2
    assert document["error"]["code"] == "response_too_large"


def test_sensitive_domain_error_details_are_redacted() -> None:
    class Request(BaseModel):
        token: str = Field(json_schema_extra={"sensitive": True})

    app = App("vault")

    @app.operation("tokens.inspect")
    def inspect(request: Request) -> EchoResult:
        raise OperationError(
            "token_rejected",
            "Token rejected",
            details=({"loc": ("token",), "input": request.token},),
        )

    result, document = invoke_json(app, ["tokens", "inspect", "--token", "consumer-secret"])

    assert result.exit_code == 4
    assert "consumer-secret" not in result.output
    assert document["error"]["details"][0]["value"] == "<redacted>"


def test_sensitive_domain_error_mapping_is_recursively_redacted() -> None:
    class Request(BaseModel):
        token: str = Field(json_schema_extra={"sensitive": True})

    app = App("vault")

    @app.operation("tokens.inspect")
    def inspect(request: Request) -> EchoResult:
        raise OperationError(
            "token_rejected",
            "Token rejected",
            details=({"context": {"provided": request.token}},),
        )

    result, _ = invoke_json(app, ["tokens", "inspect", "--token", "consumer-secret"])

    assert result.exit_code == 4
    assert "consumer-secret" not in result.output


def test_sensitive_typed_scalar_in_arbitrary_detail_key_is_redacted() -> None:
    class Request(BaseModel):
        pin: int = Field(json_schema_extra={"sensitive": True})

    app = App("vault")

    @app.operation("pins.inspect")
    def inspect(request: Request) -> EchoResult:
        raise OperationError(
            "pin_rejected",
            "PIN rejected",
            details=({"context": {"provided": request.pin}},),
        )

    result, _ = invoke_json(app, ["pins", "inspect", "--pin", "123456"])

    assert result.exit_code == 4
    assert "123456" not in result.output


def test_sensitive_boolean_in_arbitrary_detail_key_is_redacted() -> None:
    class Request(BaseModel):
        secret: bool = Field(json_schema_extra={"sensitive": True})

    app = App("vault")

    @app.operation("flags.inspect")
    def inspect(request: Request) -> EchoResult:
        raise OperationError(
            "flag_rejected",
            "Flag rejected",
            details=({"context": {"provided": request.secret}},),
        )

    result, document = invoke_json(app, ["flags", "inspect", "--secret"])

    assert result.exit_code == 4
    assert document["error"]["details"][0]["value"]["context"]["provided"] == "<redacted>"


def test_omitted_sensitive_optional_none_does_not_redact_unrelated_none_values() -> None:
    class Request(BaseModel):
        registry: Path | None = None
        edges: Path | None = None
        bws_token: str | None = Field(default=None, json_schema_extra={"sensitive": True})

    app = App("network")

    @app.operation("config.inspect")
    def inspect(request: Request) -> EchoResult:
        raise OperationError(
            "inspection_failed",
            "Configuration inspection failed",
            details=({"request": request.model_dump()},),
        )

    result, document = invoke_json(
        app,
        ["config", "inspect", "--registry", "/registry"],
    )

    assert result.exit_code == 4
    request = document["error"]["details"][0]["value"]["request"]
    assert request == {
        "registry": "/registry",
        "edges": None,
        "bws_token": "<redacted>",
    }


def test_omitted_sensitive_defaults_do_not_redact_matching_unrelated_values() -> None:
    class Request(BaseModel):
        edges: tuple[str, ...] = ()
        dry_run: bool = False
        bws_tokens: tuple[str, ...] = Field(
            default=(),
            json_schema_extra={"sensitive": True},
        )
        private_mode: bool = Field(
            default=False,
            json_schema_extra={"sensitive": True},
        )

    app = App("network")

    @app.operation("config.inspect")
    def inspect(request: Request) -> EchoResult:
        raise OperationError(
            "inspection_failed",
            "Configuration inspection failed",
            details=({"request": request.model_dump()},),
        )

    result, document = invoke_json(app, ["config", "inspect"])

    assert result.exit_code == 4
    request = document["error"]["details"][0]["value"]["request"]
    assert request == {
        "edges": [],
        "dry_run": False,
        "bws_tokens": "<redacted>",
        "private_mode": "<redacted>",
    }


def test_error_command_is_compacted_only_after_budget_failure() -> None:
    value = "x" * 300
    class LongRequest(BaseModel):
        text: str

    long_app = App("long")

    @long_app.operation("text.reject")
    def reject_long(request: LongRequest) -> EchoResult:
        raise OperationError("rejected", request.text)

    result, document = invoke_json(long_app, ["text", "reject", "--text", value])

    assert result.exit_code == 4
    assert "<value omitted" not in result.output
    assert value in document["command"]["raw"]

    class Request(BaseModel):
        tags: list[str]

    app = App("tags")

    @app.operation("tags.reject")
    def reject(request: Request) -> EchoResult:
        raise OperationError("rejected", value)

    limited, limited_document = invoke_json(
        app,
        ["tags", "reject", *sum((["--tags", str(index)] for index in range(100)), [])],
        render_options=RenderOptions(budget=OutputBudget(max_items=20)),
    )

    assert limited.exit_code == 4
    assert limited_document["error"]["code"] == "item_budget_exceeded"


def test_error_fallback_bounds_high_cardinality_parsed_mapping() -> None:
    request_model = create_model(
        "WideRequest",
        **{f"field_{index}": (str, ...) for index in range(100)},
    )
    app = App("x" * 2_000)

    def reject(request):
        raise OperationError("rejected", "Rejected")

    reject.__annotations__ = {"request": request_model, "return": EchoResult}
    app.operations.register("wide.reject", reject)
    arguments = ["wide", "reject"]
    for index in range(100):
        arguments.extend((f"--field-{index}", str(index)))

    result, document = invoke_json(
        app,
        arguments,
        render_options=RenderOptions(budget=OutputBudget(max_bytes=1_024)),
    )

    assert result.exit_code == 4
    assert document["error"]["code"] == "response_too_large"


def test_action_provider_failure_becomes_deny_by_default_internal_error() -> None:
    class BrokenActions:
        def actions_for(self, **kwargs: object) -> ActionCollection:
            raise RuntimeError("provider private detail")

        def list_actions(self, **kwargs: object) -> ActionCollection:
            raise RuntimeError("provider private detail")

        def explain(self, operation: str):
            raise RuntimeError("provider private detail")

    result, document = invoke_json(
        echo_app(),
        ["message", "echo", "--text", "hello"],
        action_provider=BrokenActions(),
    )

    assert result.exit_code == 70
    assert document["error"]["code"] == "internal_error"
    assert document["next_actions"]["items"] == []
    assert "provider private detail" not in result.output


def test_required_confirmation_field_uses_confirmation_exit() -> None:
    class Request(BaseModel):
        item: str
        confirm: bool

    app = App("inventory")

    @app.operation("items.delete", destructive=True)
    def delete(request: Request) -> EchoResult:
        return EchoResult(message=request.item)

    result, document = invoke_json(app, ["items", "delete", "--item", "one"])

    assert result.exit_code == 3
    assert document["error"]["code"] == "confirmation_required"


def test_transport_confirmation_is_present_in_parsed_flags() -> None:
    class Request(BaseModel):
        item: str

    app = App("inventory")

    @app.operation("items.delete", destructive=True)
    def delete(request: Request) -> EchoResult:
        return EchoResult(message=request.item)

    result, document = invoke_json(app, ["items", "delete", "--item", "one", "--confirm"])

    assert result.exit_code == 0
    assert "confirm" in document["command"]["parsed"]["flags"]


@pytest.mark.parametrize(
    ("argument", "value", "error_code"),
    [
        ("--score", "nan", "usage_error"),
        ("--score", "inf", "usage_error"),
        ("--score=-1e999", None, "usage_error"),
    ],
)
def test_non_finite_float_is_rejected(
    argument: str,
    value: str | None,
    error_code: str,
) -> None:
    class Request(BaseModel):
        score: float

    app = App("scores")

    @app.operation("scores.record")
    def record(request: Request) -> EchoResult:
        return EchoResult(message=str(request.score))

    args = ["scores", "record", argument]
    if value is not None:
        args.append(value)
    result, document = invoke_json(app, args)

    assert result.exit_code == 2
    assert document["error"]["code"] == error_code
