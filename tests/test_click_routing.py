from enum import StrEnum
from pathlib import Path

import click
from click.testing import CliRunner
from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from agent_surface import App
from agent_surface.adapters.click import ClickAdapter, build_click_group


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
