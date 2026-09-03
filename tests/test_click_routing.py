import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

import click
import pytest
from click.testing import CliRunner
from pydantic import BaseModel, Field, create_model
from ruamel.yaml import YAML

from agent_surface import App, CanonicalEnvelopeRenderer, ComposedApp, Invocation, OperationError
from agent_surface.adapters.click import ClickAdapter, build_click_group
from agent_surface.envelopes import public_request


class Mode(StrEnum):
    FAST = "fast"
    SAFE = "safe"


class Request(BaseModel):
    book: str = Field(json_schema_extra={"cli": {"kind": "argument"}})
    count: int = 1
    enabled: bool = True
    tag: list[str] = Field(default_factory=list)
    mode: Mode = Mode.SAFE
    output: Path | None = None


class Result(BaseModel):
    status: str


class ConsumerEnvelope(BaseModel):
    schema_version: Literal["consumer.cli/v1"] = "consumer.cli/v1"
    operation: str
    error_code: str | None


class ConsumerRenderer(CanonicalEnvelopeRenderer):
    output_model = ConsumerEnvelope

    def render(self, invocation: Invocation) -> ConsumerEnvelope:
        return ConsumerEnvelope(
            operation=invocation.operation.name,
            error_code=invocation.error.code if invocation.error is not None else None,
        )


def app() -> App:
    value = App("bookstore", version="1.2.3")

    @value.operation("books.inspect", summary="Inspect one book", read_only=True)
    def inspect(request: Request) -> Result:
        return Result(status=request.book)

    return value


def test_generates_nested_click_groups_with_concise_help() -> None:
    command = build_click_group(app())

    result = CliRunner().invoke(command, ["books", "inspect", "--help"])

    assert result.exit_code == 0
    assert "Inspect one book" in result.output
    assert "--count INTEGER" in result.output
    assert "--enabled / --no-enabled" in result.output
    assert "--tag TEXT" in result.output
    assert "--mode [fast|safe]" in result.output
    assert "--output PATH" in result.output


def test_generated_group_mounts_beneath_a_consumer_owned_group() -> None:
    root = click.Group("root")
    root.add_command(build_click_group(app()), name="catalog")

    result = CliRunner().invoke(root, ["catalog", "books", "inspect", "--help"])

    assert result.exit_code == 0
    assert "Inspect one book" in result.output


class RenderShared(BaseModel):
    profile: str


class ProjectShared(BaseModel):
    region: str


class RenderRequest(RenderShared):
    value: str


class ProjectRequest(ProjectShared):
    target: str


def test_composed_click_tree_keeps_child_shared_inputs_local() -> None:
    render_app = App("render", shared_input_model=RenderShared)
    project_app = App("project", shared_input_model=ProjectShared)

    @render_app.operation("render")
    def render_diagram(request: RenderRequest) -> Result:
        return Result(status=f"{request.profile}:{request.value}")

    @project_app.operation("build")
    def build_project(request: ProjectRequest) -> Result:
        return Result(status=f"{request.region}:{request.target}")

    surface = (
        ComposedApp("infralink")
        .mount("diagram", render_app)
        .mount("diagram.project", project_app)
    )

    command = build_click_group(surface)

    render_result = CliRunner().invoke(
        command, ["diagram", "--profile", "draft", "render", "--value", "topology"]
    )
    project_result = CliRunner().invoke(
        command,
        ["diagram", "project", "--region", "us-east-1", "build", "--target", "alpha"],
    )
    invalid_result = CliRunner().invoke(
        command, ["diagram", "render", "--region", "us-east-1", "--value", "topology"]
    )
    discovery_result = CliRunner().invoke(command, ["operations", "list"])

    assert render_result.exit_code == 0
    assert YAML(typ="safe").load(render_result.stdout)["result"] == {
        "status": "draft:topology"
    }
    assert project_result.exit_code == 0
    assert YAML(typ="safe").load(project_result.stdout)["result"] == {
        "status": "us-east-1:alpha"
    }
    invalid_document = YAML(typ="safe").load(invalid_result.stdout)
    assert invalid_result.exit_code == 2
    assert invalid_document["error"]["code"] == "usage_error"
    assert discovery_result.exit_code == 0
    assert [
        item["name"]
        for item in YAML(typ="safe").load(discovery_result.stdout)["result"]["items"]
    ] == ["diagram.project.build", "diagram.render"]


def test_mounted_group_uses_explicit_provider_for_original_outer_argv() -> None:
    original = (
        "root",
        "--profile",
        "prod",
        "catalog",
        "books",
        "inspect",
        "dune",
    )
    root = click.Group(
        "root",
        params=[click.Option(("--profile",), expose_value=False)],
    )
    root.add_command(
        ClickAdapter(app(), argv_provider=lambda: original).command(),
        name="catalog",
    )

    result = CliRunner().invoke(root, list(original[1:]))
    document = YAML(typ="safe").load(result.stdout)

    assert result.exit_code == 0
    assert tuple(document["command"]["raw"]) == original


def test_mounted_parse_error_uses_consumer_envelope_and_parent_output() -> None:
    original = (
        "root",
        "--output",
        "json",
        "resolve",
        "books",
        "inspect",
        "dune",
        "--count",
        "not-an-integer",
    )
    root = click.Group(
        "root",
        params=[click.Option(("--output",), type=click.Choice(("yaml", "json")))],
    )
    root.add_command(
        ClickAdapter(
            app(),
            argv_provider=lambda: original,
            envelope_renderer=ConsumerRenderer(),
        ).command(),
        name="resolve",
    )

    result = CliRunner().invoke(root, list(original[1:]))

    assert result.exit_code == 2
    assert json.loads(result.output) == {
        "schema_version": "consumer.cli/v1",
        "operation": "books.inspect",
        "error_code": "usage_error",
    }


def test_mounted_unknown_option_uses_consumer_envelope_and_parent_format() -> None:
    original = (
        "root",
        "--format",
        "json",
        "resolve",
        "books",
        "inspect",
        "dune",
        "--unknown-option",
        "value",
    )
    root = click.Group(
        "root",
        params=[click.Option(("--format",), type=click.Choice(("yaml", "json")))],
    )
    root.add_command(
        ClickAdapter(
            app(),
            argv_provider=lambda: original,
            envelope_renderer=ConsumerRenderer(),
        ).command(),
        name="resolve",
    )

    result = CliRunner().invoke(root, list(original[1:]))

    assert result.exit_code == 2
    assert json.loads(result.output) == {
        "schema_version": "consumer.cli/v1",
        "operation": "books.inspect",
        "error_code": "usage_error",
    }


def test_public_request_does_not_redact_unrelated_default_none_values() -> None:
    class SensitiveRequest(BaseModel):
        registry: Path | None = None
        token: str | None = Field(default=None, json_schema_extra={"sensitive": True})

    surface = App("network")

    @surface.operation("config.inspect")
    def inspect(request: SensitiveRequest) -> Result:
        return Result(status=str(request.registry))

    definition = surface.operations.describe("config.inspect")

    assert public_request(definition, SensitiveRequest()) == {
        "registry": None,
        "token": "<redacted>",
    }


def test_canonical_error_redacts_non_sensitive_value_equal_to_supplied_secret() -> None:
    class SensitiveRequest(BaseModel):
        token: str = Field(json_schema_extra={"sensitive": True})
        mirror: str

    class ErrorEnvelope(BaseModel):
        request: dict[str, str] | None

    class ErrorRenderer(CanonicalEnvelopeRenderer):
        output_model = ErrorEnvelope

        def render(self, invocation: Invocation) -> ErrorEnvelope:
            return ErrorEnvelope(
                request=(dict(invocation.request) if invocation.request is not None else None)
            )

    surface = App("network")

    @surface.operation("config.inspect")
    def inspect(request: SensitiveRequest) -> Result:
        raise OperationError("inspection_failed", "Configuration inspection failed")

    result = CliRunner().invoke(
        ClickAdapter(surface, envelope_renderer=ErrorRenderer()).command(),
        [
            "config",
            "inspect",
            "--token",
            "top-secret",
            "--mirror",
            "top-secret",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 4
    assert "top-secret" not in result.output
    assert json.loads(result.output) == {
        "request": {"token": "<redacted>", "mirror": "<redacted>"},
    }


def test_generated_click_parameter_shapes_match_the_compiled_plan() -> None:
    root = ClickAdapter(app()).command()
    books = root.commands["books"]
    assert isinstance(books, click.Group)
    inspect_command = books.commands["inspect"]
    parameters = {parameter.name: parameter for parameter in inspect_command.params}

    assert isinstance(parameters["book"], click.Argument)
    assert parameters["book"].required is True
    assert parameters["count"].type is click.INT
    assert isinstance(parameters["enabled"], click.Option)
    assert parameters["enabled"].is_bool_flag is True
    assert parameters["enabled"].secondary_opts == ["--no-enabled"]
    assert parameters["tag"].multiple is True
    assert isinstance(parameters["mode"].type, click.Choice)
    assert parameters["mode"].type.choices == ("fast", "safe")
    assert isinstance(parameters["output"].type, click.Path)


@pytest.mark.parametrize(
    ("bounds", "expected_min", "expected_max", "invalid_value"),
    [
        ({"ge": 1, "le": 3}, 1, 3, "0"),
        ({"ge": 1}, 1, None, "0"),
        ({"le": 3}, None, 3, "4"),
    ],
)
def test_constrained_integer_option_preserves_pydantic_bounds_in_click(
    bounds: dict[str, int],
    expected_min: int | None,
    expected_max: int | None,
    invalid_value: str,
) -> None:
    request_model = create_model(
        "ConstrainedIntegerRequest",
        value=(int, Field(default=2, **bounds)),
    )
    app = App("numbers")

    @app.operation("numbers.check")
    def check(request: request_model) -> Result:  # type: ignore[valid-type]
        return Result(status=str(request.value))

    command = build_click_group(app)
    numbers = command.commands["numbers"]
    assert isinstance(numbers, click.Group)
    check_command = numbers.commands["check"]
    value = next(parameter for parameter in check_command.params if parameter.name == "value")

    assert isinstance(value.type, click.IntRange)
    assert value.type.min == expected_min
    assert value.type.max == expected_max

    help_result = CliRunner().invoke(command, ["numbers", "check", "--help"])
    assert help_result.exit_code == 0
    assert "--value INTEGER RANGE" in help_result.output

    invalid_result = CliRunner().invoke(
        command,
        ["numbers", "check", "--value", invalid_value, "--format", "json"],
    )
    assert invalid_result.exit_code == 2
    invalid_document = YAML(typ="safe").load(invalid_result.output)
    assert invalid_document["error"]["code"] == "usage_error"
