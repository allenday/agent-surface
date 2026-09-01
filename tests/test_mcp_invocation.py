import json
from dataclasses import dataclass

import pytest
from mcp import Client
from pydantic import BaseModel, Field

from agent_surface import (
    ActionCollection,
    App,
    OperationError,
    OperationOutcome,
    OutputBudget,
    ReferenceRegistry,
    RenderOptions,
)
from agent_surface.adapters.mcp import MCPAdapter


class EchoRequest(BaseModel):
    text: str
    count: int = Field(default=1, ge=1, le=3)


class EchoResult(BaseModel):
    message: str


def echo_app() -> App:
    app = App("echo")

    @app.operation("message.echo", read_only=True)
    async def echo(request: EchoRequest) -> EchoResult:
        if request.text == "missing":
            raise OperationError(
                "message_missing",
                "Message was not found",
                fix="Choose another message.",
            )
        if request.text == "explode":
            raise RuntimeError("private traceback detail")
        return EchoResult(message=request.text * request.count)

    return app


@pytest.mark.asyncio
async def test_call_tool_returns_authoritative_structured_success_and_yaml_text() -> None:
    adapter = MCPAdapter(echo_app())

    async with Client(adapter.server, raise_exceptions=True) as client:
        result = await client.call_tool("message.echo", {"text": "hello", "count": 2})

    assert result.is_error is False
    assert result.structured_content["ok"] is True
    assert result.structured_content["result"] == {"message": "hellohello"}
    assert result.structured_content["next_actions"]["items"] == []
    assert result.content[0].text.startswith("schema_version:")
    assert "ok: true" in result.content[0].text


@pytest.mark.asyncio
async def test_action_provider_receives_validated_request_context() -> None:
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
    adapter = MCPAdapter(echo_app(), action_provider=actions)

    async with Client(adapter.server, raise_exceptions=True) as client:
        result = await client.call_tool("message.echo", {"text": "hello", "count": 2})

    assert result.is_error is False
    assert actions.requests == [EchoRequest(text="hello", count=2)]


@pytest.mark.asyncio
async def test_legacy_action_provider_without_request_remains_supported() -> None:
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
    adapter = MCPAdapter(echo_app(), action_provider=actions)

    async with Client(adapter.server, raise_exceptions=True) as client:
        result = await client.call_tool("message.echo", {"text": "hello"})

    assert result.is_error is False
    assert result.structured_content["result"] == {"message": "hello"}
    assert actions.operations == ["message.echo"]


@pytest.mark.asyncio
async def test_action_provider_receives_no_request_for_validation_failure() -> None:
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
    adapter = MCPAdapter(echo_app(), action_provider=actions)

    async with Client(adapter.server, raise_exceptions=True) as client:
        result = await client.call_tool("message.echo", {"text": "hello", "count": 9})

    assert result.is_error is True
    assert actions.requests == [None]


@pytest.mark.asyncio
async def test_successful_negative_outcome_remains_an_mcp_success() -> None:
    app = App("status")

    @app.operation("operation.status")
    def status(request: EchoRequest) -> OperationOutcome[EchoResult]:
        return OperationOutcome(EchoResult(message=request.text), exit_code=1)

    adapter = MCPAdapter(app)
    async with Client(adapter.server, raise_exceptions=True) as client:
        result = await client.call_tool("operation.status", {"text": "failed"})

    assert result.is_error is False
    assert result.structured_content["ok"] is True
    assert result.structured_content["result"] == {"message": "failed"}


@pytest.mark.asyncio
async def test_input_domain_and_internal_failures_are_structured() -> None:
    adapter = MCPAdapter(echo_app())

    async with Client(adapter.server, raise_exceptions=True) as client:
        invalid = await client.call_tool("message.echo", {"text": "hello", "count": 9})
        missing = await client.call_tool("message.echo", {"text": "missing"})
        internal = await client.call_tool("message.echo", {"text": "explode"})

    assert invalid.is_error is True
    assert invalid.structured_content["error"]["code"] == "invalid_input"
    assert missing.is_error is True
    assert missing.structured_content["error"]["code"] == "message_missing"
    assert missing.structured_content["fix"] == "Choose another message."
    assert internal.is_error is True
    assert internal.structured_content["error"]["code"] == "internal_error"
    assert "private traceback detail" not in internal.content[0].text


@pytest.mark.asyncio
async def test_destructive_tool_requires_transport_confirmation_before_invocation() -> None:
    class Request(BaseModel):
        item: str

    calls = 0
    app = App("inventory")

    @app.operation("items.delete", destructive=True)
    def delete(request: Request) -> EchoResult:
        nonlocal calls
        calls += 1
        return EchoResult(message=request.item)

    adapter = MCPAdapter(app)
    async with Client(adapter.server, raise_exceptions=True) as client:
        denied = await client.call_tool("items.delete", {"item": "one"})
        allowed = await client.call_tool("items.delete", {"item": "one", "confirm": True})

    assert denied.is_error is True
    assert denied.structured_content["error"]["code"] == "confirmation_required"
    assert allowed.is_error is False
    assert calls == 1


@pytest.mark.asyncio
async def test_reference_tokens_decode_before_domain_invocation() -> None:
    @dataclass(frozen=True)
    class BookRef:
        value: str

    class Codec:
        kind = "book"
        python_type = BookRef

        def encode(self, value: BookRef) -> str:
            return value.value

        def decode(self, token: str) -> BookRef:
            return BookRef(token)

        def display(self, value: BookRef) -> str:
            return value.value

    class Request(BaseModel):
        book: BookRef

    app = App("books")

    @app.operation("books.inspect")
    def inspect(request: Request) -> EchoResult:
        return EchoResult(message=request.book.value)

    references = ReferenceRegistry()
    references.register(Codec())
    adapter = MCPAdapter(app, references=references)

    async with Client(adapter.server, raise_exceptions=True) as client:
        tools = await client.list_tools()
        result = await client.call_tool("books.inspect", {"book": "book_dune"})

    book_schema = tools.tools[0].input_schema["properties"]["book"]
    assert book_schema["type"] == "string"
    assert result.structured_content["result"] == {"message": "book_dune"}


@pytest.mark.asyncio
async def test_reference_codec_failure_is_a_stable_invalid_reference() -> None:
    @dataclass(frozen=True)
    class BookRef:
        value: str

    class RejectingCodec:
        kind = "book"
        python_type = BookRef

        def encode(self, value: BookRef) -> str:
            return value.value

        def decode(self, token: str) -> BookRef:
            raise ValueError("private codec detail")

        def display(self, value: BookRef) -> str:
            return value.value

    class Request(BaseModel):
        book: BookRef

    app = App("books")

    @app.operation("books.inspect")
    def inspect(request: Request) -> EchoResult:
        return EchoResult(message=request.book.value)

    references = ReferenceRegistry()
    references.register(RejectingCodec())
    adapter = MCPAdapter(app, references=references)

    async with Client(adapter.server, raise_exceptions=True) as client:
        result = await client.call_tool("books.inspect", {"book": "missing"})

    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "invalid_reference"
    assert "private codec detail" not in result.content[0].text


@pytest.mark.asyncio
async def test_sensitive_reference_token_is_redacted_from_reference_errors() -> None:
    @dataclass(frozen=True)
    class BookRef:
        value: str

    class UnstableCodec:
        kind = "book"
        python_type = BookRef

        def encode(self, value: BookRef) -> str:
            return value.value

        def decode(self, token: str) -> BookRef:
            return BookRef(f"changed-{token}")

        def display(self, value: BookRef) -> str:
            return value.value

    class Request(BaseModel):
        book: BookRef = Field(json_schema_extra={"sensitive": True})

    app = App("books")

    @app.operation("books.inspect")
    def inspect(request: Request) -> EchoResult:
        return EchoResult(message=request.book.value)

    references = ReferenceRegistry()
    references.register(UnstableCodec())
    adapter = MCPAdapter(app, references=references)

    async with Client(adapter.server, raise_exceptions=True) as client:
        result = await client.call_tool(
            "books.inspect", {"book": "consumer-secret"}
        )

    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "invalid_reference"
    assert "consumer-secret" not in result.content[0].text
    assert "consumer-secret" not in str(result.structured_content)


@pytest.mark.asyncio
async def test_sensitive_domain_details_are_recursively_redacted() -> None:
    class Request(BaseModel):
        token: str = Field(json_schema_extra={"sensitive": True})

    app = App("vault")

    @app.operation("tokens.inspect")
    def inspect(request: Request) -> EchoResult:
        raise OperationError(
            "token_rejected",
            f"Token {request.token} rejected",
            details=({"context": {"provided": f"value {request.token}"}},),
            fix=f"Remove {request.token} and retry",
        )

    adapter = MCPAdapter(app)
    async with Client(adapter.server, raise_exceptions=True) as client:
        result = await client.call_tool("tokens.inspect", {"token": "consumer-secret"})

    assert result.is_error is True
    assert "consumer-secret" not in result.content[0].text
    assert "consumer-secret" not in str(result.structured_content)


def test_mcp_adapter_rejects_budget_too_small_for_structured_errors() -> None:
    with pytest.raises(ValueError, match="at least 1024 bytes"):
        MCPAdapter(
            echo_app(),
            render_options=RenderOptions(budget=OutputBudget(max_bytes=100)),
        )


@pytest.mark.asyncio
async def test_combined_text_and_structured_content_obey_the_byte_budget() -> None:
    adapter = MCPAdapter(
        echo_app(),
        render_options=RenderOptions(budget=OutputBudget(max_bytes=1_024)),
    )

    async with Client(adapter.server, raise_exceptions=True) as client:
        result = await client.call_tool("message.echo", {"text": "x" * 500})

    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "response_too_large"
    public_bytes = len(result.content[0].text.encode()) + len(
        json.dumps(
            result.structured_content,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    )
    assert public_bytes <= 1_024
