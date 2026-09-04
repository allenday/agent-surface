"""Application-owned canonical envelopes must project through every adapter."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from click.testing import CliRunner
from mcp import Client
from pydantic import BaseModel, Field

from agent_surface import (
    App,
    CanonicalEnvelopeRenderer,
    ComposedApp,
    Invocation,
    OperationError,
    OutputBudget,
    RenderOptions,
)
from agent_surface.adapters.click import ClickAdapter, build_click_group
from agent_surface.adapters.mcp import MCPAdapter


class EchoRequest(BaseModel):
    text: str


class EchoResult(BaseModel):
    message: str


class SensitiveEchoRequest(BaseModel):
    text: str
    token: str = Field(json_schema_extra={"sensitive": True})


class ConsumerEnvelope(BaseModel):
    schema_version: Literal["consumer.example/v1"] = "consumer.example/v1"
    ok: bool
    operation: str
    request: dict[str, object] | None
    result: dict[str, object] | None
    error_code: str | None
    next_action_count: int
    max_bytes: int


class ConsumerRenderer(CanonicalEnvelopeRenderer):
    output_model = ConsumerEnvelope

    def render(self, invocation: Invocation) -> ConsumerEnvelope:
        return ConsumerEnvelope(
            ok=invocation.error is None,
            operation=invocation.operation.name,
            request=(
                dict(invocation.request)
                if invocation.request is not None
                else None
            ),
            result=(
                invocation.result.model_dump(mode="json") if invocation.result is not None else None
            ),
            error_code=invocation.error.code if invocation.error is not None else None,
            next_action_count=invocation.next_actions.returned,
            max_bytes=invocation.budget.max_bytes,
        )


class FixEnvelope(BaseModel):
    operation: str
    fix: str | None


class FixRenderer(CanonicalEnvelopeRenderer):
    output_model = FixEnvelope

    def render(self, invocation: Invocation) -> FixEnvelope:
        return FixEnvelope(
            operation=invocation.operation.name,
            fix=invocation.error.fix if invocation.error is not None else None,
        )


class CommandEnvelope(ConsumerEnvelope):
    command: dict[str, object] | None


class CommandRenderer(CanonicalEnvelopeRenderer):
    output_model = CommandEnvelope

    def render(self, invocation: Invocation) -> CommandEnvelope:
        return CommandEnvelope(
            ok=invocation.error is None,
            operation=invocation.operation.name,
            request=(dict(invocation.request) if invocation.request is not None else None),
            result=(
                invocation.result.model_dump(mode="json") if invocation.result is not None else None
            ),
            error_code=invocation.error.code if invocation.error is not None else None,
            next_action_count=invocation.next_actions.returned,
            max_bytes=invocation.budget.max_bytes,
            command=(
                invocation.command.model_dump(mode="json")
                if invocation.command is not None
                else None
            ),
        )


def app() -> App:
    surface = App("example")

    @surface.operation("echo", read_only=True)
    def echo(request: EchoRequest) -> EchoResult:
        if request.text == "missing":
            raise OperationError("missing", "No echo is available")
        return EchoResult(message=request.text)

    return surface


def test_custom_canonical_envelope_projects_same_success_through_click_and_mcp() -> None:
    renderer = ConsumerRenderer()
    click_result = CliRunner().invoke(
        ClickAdapter(app(), envelope_renderer=renderer).command(),
        ["echo", "--text", "hello", "--format", "json"],
    )

    async def call_mcp() -> dict[str, object]:
        async with Client(MCPAdapter(app(), envelope_renderer=renderer).server) as client:
            result = await client.call_tool("echo", {"text": "hello"})
        assert result.is_error is False
        return result.structured_content

    assert click_result.exit_code == 0, click_result.output
    click_document = json.loads(click_result.output)
    mcp_document = asyncio.run(call_mcp())
    expected = {
        "schema_version": "consumer.example/v1",
        "ok": True,
        "operation": "echo",
        "request": {"text": "hello"},
        "result": {"message": "hello"},
        "error_code": None,
        "next_action_count": 0,
        "max_bytes": 65_536,
    }
    assert click_document == expected
    assert mcp_document == expected


def test_composed_click_canonical_renderer_receives_public_operation_name() -> None:
    child = App("diagram")

    @child.operation("project", read_only=True)
    def project(request: EchoRequest) -> EchoResult:
        return EchoResult(message=request.text)

    command = build_click_group(
        ComposedApp("infralink").mount(
            "diagram", child, click={"envelope_renderer": ConsumerRenderer()}
        ),
    )

    result = CliRunner().invoke(
        command,
        ["diagram", "project", "--text", "hello", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["operation"] == "diagram.project"


def test_composed_click_canonical_parse_error_uses_public_operation_name() -> None:
    child = App("diagram")

    @child.operation("project", read_only=True)
    def project(request: EchoRequest) -> EchoResult:
        return EchoResult(message=request.text)

    command = build_click_group(
        ComposedApp("infralink").mount(
            "diagram", child, click={"envelope_renderer": FixRenderer()}
        ),
    )

    result = CliRunner().invoke(
        command,
        ["diagram", "project", "--unknown", "value", "--format", "json"],
    )

    assert result.exit_code == 2, result.output
    document = json.loads(result.output)
    assert document["operation"] == "diagram.project"
    assert document["fix"] == "Run infralink operations describe diagram.project."


def test_root_parse_error_uses_the_configured_canonical_renderer() -> None:
    result = CliRunner().invoke(
        ClickAdapter(app(), envelope_renderer=ConsumerRenderer()).command(),
        ["--unknown", "value", "--format", "json"],
    )

    assert result.exit_code == 2, result.output
    document = json.loads(result.output)
    assert document["schema_version"] == "consumer.example/v1"
    assert document["error_code"] == "usage_error"


def test_discovery_parse_error_uses_canonical_renderer_and_redacts_unknown_value() -> None:
    result = CliRunner().invoke(
        ClickAdapter(app(), envelope_renderer=ConsumerRenderer()).command(),
        ["operations", "list", "--format-secret=canary-secret", "--format", "json"],
    )

    assert result.exit_code == 2, result.output
    document = json.loads(result.output)
    assert document["schema_version"] == "consumer.example/v1"
    assert document["error_code"] == "usage_error"
    assert "canary-secret" not in result.output


def test_custom_canonical_envelope_projects_same_expected_error_through_click_and_mcp() -> None:
    renderer = ConsumerRenderer()
    click_result = CliRunner().invoke(
        ClickAdapter(app(), envelope_renderer=renderer).command(),
        ["echo", "--text", "missing", "--format", "json"],
    )

    async def call_mcp() -> dict[str, object]:
        async with Client(MCPAdapter(app(), envelope_renderer=renderer).server) as client:
            result = await client.call_tool("echo", {"text": "missing"})
        assert result.is_error is True
        return result.structured_content

    assert click_result.exit_code == 4, click_result.output
    click_document = json.loads(click_result.output)
    mcp_document = asyncio.run(call_mcp())
    expected = {
        "schema_version": "consumer.example/v1",
        "ok": False,
        "operation": "echo",
        "request": {"text": "missing"},
        "result": None,
        "error_code": "missing",
        "next_action_count": 0,
        "max_bytes": 65_536,
    }
    assert click_document == expected
    assert mcp_document == expected


def test_custom_canonical_envelope_preserves_its_schema_for_mcp_budget_errors() -> None:
    oversized = "x" * 2_000
    surface = App("example")

    @surface.operation("echo", read_only=True)
    def echo(request: EchoRequest) -> EchoResult:
        return EchoResult(message=oversized)

    async def call_mcp() -> dict[str, object]:
        adapter = MCPAdapter(
            surface,
            envelope_renderer=ConsumerRenderer(),
            render_options=RenderOptions(budget=OutputBudget(max_bytes=1_024)),
        )
        async with Client(adapter.server) as client:
            result = await client.call_tool("echo", {"text": "hello"})
        assert result.is_error is True
        return result.structured_content

    document = asyncio.run(call_mcp())
    assert document["schema_version"] == "consumer.example/v1"
    assert document["ok"] is False
    assert document["error_code"] == "response_too_large"
    assert document["result"] is None


def test_custom_canonical_envelope_redacts_sensitive_request_fields() -> None:
    secret = "top-secret-token"
    surface = App("example")

    @surface.operation("echo", read_only=True)
    def echo(request: SensitiveEchoRequest) -> EchoResult:
        return EchoResult(message=request.text)

    renderer = ConsumerRenderer()
    click_result = CliRunner().invoke(
        ClickAdapter(surface, envelope_renderer=renderer).command(),
        ["echo", "--text", "hello", "--token", secret, "--format", "json"],
    )

    async def call_mcp() -> dict[str, object]:
        async with Client(MCPAdapter(surface, envelope_renderer=renderer).server) as client:
            result = await client.call_tool("echo", {"text": "hello", "token": secret})
        assert result.is_error is False
        return result.structured_content

    assert click_result.exit_code == 0, click_result.output
    assert secret not in click_result.output
    assert json.loads(click_result.output)["request"] == {
        "text": "hello",
        "token": "<redacted>",
    }
    mcp_document = asyncio.run(call_mcp())
    assert secret not in json.dumps(mcp_document)
    assert mcp_document["request"] == {"text": "hello", "token": "<redacted>"}


def test_custom_canonical_envelope_bounds_oversized_request_for_click_and_mcp() -> None:
    oversized = "x" * 2_000
    surface = App("example")

    @surface.operation("echo", read_only=True)
    def echo(request: EchoRequest) -> EchoResult:
        return EchoResult(message="ok")

    options = RenderOptions(budget=OutputBudget(max_bytes=1_024))
    click_adapter = ClickAdapter(
        surface,
        envelope_renderer=ConsumerRenderer(),
        render_options=options,
    )
    click_result = CliRunner().invoke(
        click_adapter.command(),
        ["echo", "--text", oversized, "--format", "json"],
    )

    async def call_mcp() -> dict[str, object]:
        adapter = MCPAdapter(
            surface,
            envelope_renderer=ConsumerRenderer(),
            render_options=options,
        )
        async with Client(adapter.server) as client:
            result = await client.call_tool("echo", {"text": oversized})
        assert result.is_error is True
        return result.structured_content

    assert click_result.exit_code == 70, click_result.output
    click_document = json.loads(click_result.output)
    mcp_document = asyncio.run(call_mcp())
    for document in (click_document, mcp_document):
        assert document["ok"] is False
        assert document["error_code"] == "response_too_large"
        assert document["request"] is None
        assert document["result"] is None


def test_custom_canonical_envelope_bounds_oversized_error_for_click_and_mcp() -> None:
    oversized = "x" * 2_000
    surface = App("example")

    @surface.operation("echo", read_only=True)
    def echo(request: EchoRequest) -> EchoResult:
        raise OperationError("missing", "No echo is available")

    options = RenderOptions(budget=OutputBudget(max_bytes=1_024))
    click_adapter = ClickAdapter(
        surface,
        envelope_renderer=ConsumerRenderer(),
        render_options=options,
    )
    click_result = CliRunner().invoke(
        click_adapter.command(),
        ["echo", "--text", oversized, "--format", "json"],
    )

    async def call_mcp() -> dict[str, object]:
        adapter = MCPAdapter(
            surface,
            envelope_renderer=ConsumerRenderer(),
            render_options=options,
        )
        async with Client(adapter.server) as client:
            result = await client.call_tool("echo", {"text": oversized})
        assert result.is_error is True
        return result.structured_content

    assert click_result.exit_code == 4, click_result.output
    click_document = json.loads(click_result.output)
    mcp_document = asyncio.run(call_mcp())
    for document in (click_document, mcp_document):
        assert document["ok"] is False
        assert document["error_code"] == "response_too_large"
        assert document["request"] is None
        assert document["result"] is None


def test_custom_canonical_envelope_bounds_oversized_click_command() -> None:
    oversized = "x" * 2_000
    surface = App("example")

    @surface.operation("echo", read_only=True)
    def echo(request: EchoRequest) -> EchoResult:
        return EchoResult(message="ok")

    adapter = ClickAdapter(
        surface,
        envelope_renderer=CommandRenderer(),
        render_options=RenderOptions(budget=OutputBudget(max_bytes=1_024)),
    )
    result = CliRunner().invoke(
        adapter.command(),
        ["echo", "--text", oversized, "--format", "json"],
    )

    assert result.exit_code == 70, result.output
    document = json.loads(result.output)
    assert document["ok"] is False
    assert document["error_code"] == "response_too_large"
    assert document["request"] is None
    assert document["result"] is None
    assert document["command"] is None
