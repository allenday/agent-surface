from enum import StrEnum
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, Field, StrictInt

from agent_surface import App, ReferenceRegistry
from agent_surface.adapters.click import CliDefinitionError, CliPlanCompiler


class Mode(StrEnum):
    FAST = "fast"
    SAFE = "safe"


class Result(BaseModel):
    status: str


class Request(BaseModel):
    query: str = Field(description="Search text")
    count: StrictInt = Field(default=2, ge=1, le=10)
    enabled: bool = True
    tag: list[str] = Field(default_factory=list)
    mode: Mode = Mode.SAFE
    output: Path | None = None
    category: Literal["fiction", "nonfiction"] = "fiction"
    secret: str = Field(default="token", json_schema_extra={"sensitive": True})


def app_for(request_model: type[BaseModel] = Request) -> App:
    app = App("catalog")

    @app.operation("books.search", summary="Search books", read_only=True)
    def search(request: request_model) -> Result:  # type: ignore[valid-type]
        return Result(status="ok")

    return app


def test_compiles_dotted_operation_and_field_metadata() -> None:
    plan = CliPlanCompiler(app_for().operations).compile()[0]

    assert plan.operation == "books.search"
    assert plan.path == ("books", "search")
    assert plan.summary == "Search books"
    assert plan.read_only is True
    assert [field.name for field in plan.fields] == list(Request.model_fields)
    assert plan.fields[0].parameter_decls == ("--query",)
    assert plan.fields[0].help == "Search text"
    assert plan.fields[-1].sensitive is True


def test_compiles_lossless_lexical_field_kinds() -> None:
    plan = CliPlanCompiler(app_for().operations).compile()[0]
    fields = {field.name: field for field in plan.fields}

    assert fields["query"].value_kind == "string"
    assert fields["count"].value_kind == "integer"
    assert fields["enabled"].value_kind == "boolean"
    assert fields["tag"].value_kind == "string"
    assert fields["tag"].multiple is True
    assert fields["mode"].choices == ("fast", "safe")
    assert fields["output"].value_kind == "path"
    assert fields["output"].required is False
    assert fields["category"].choices == ("fiction", "nonfiction")


def test_explicit_argument_metadata_changes_only_the_declared_field() -> None:
    class ArgumentRequest(BaseModel):
        book: str = Field(json_schema_extra={"cli": {"kind": "argument"}})
        detail: bool = False

    fields = CliPlanCompiler(app_for(ArgumentRequest).operations).compile()[0].fields

    assert fields[0].kind == "argument"
    assert fields[0].parameter_decls == ("book",)
    assert fields[1].kind == "option"


def test_registered_exact_reference_type_compiles_as_reference() -> None:
    class BookRef(BaseModel):
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

    class RefRequest(BaseModel):
        book: BookRef

    references = ReferenceRegistry()
    references.register(BookCodec())

    plan = CliPlanCompiler(
        app_for(RefRequest).operations,
        references=references,
    ).compile()[0]
    field = plan.fields[0]

    assert field.value_kind == "reference"
    assert field.reference_type is BookRef


@pytest.mark.parametrize("name", ["operations.list", "actions.explain"])
def test_reserved_generated_names_fail_during_compilation(name: str) -> None:
    app = App("conflict")

    @app.operation(name)
    def conflict(request: Request) -> Result:
        return Result(status="no")

    with pytest.raises(CliDefinitionError) as raised:
        CliPlanCompiler(app.operations).compile()

    assert raised.value.code == "cli_command_conflict"


def test_leaf_and_group_conflict_fails_during_compilation() -> None:
    app = App("conflict")

    @app.operation("books")
    def books(request: Request) -> Result:
        return Result(status="no")

    @app.operation("books.search")
    def search(request: Request) -> Result:
        return Result(status="no")

    with pytest.raises(CliDefinitionError, match="books") as raised:
        CliPlanCompiler(app.operations).compile()

    assert raised.value.code == "cli_command_conflict"


def test_unregistered_nested_model_fails_instead_of_stringifying() -> None:
    class Nested(BaseModel):
        value: str

    class NestedRequest(BaseModel):
        nested: Nested

    with pytest.raises(CliDefinitionError) as raised:
        CliPlanCompiler(app_for(NestedRequest).operations).compile()

    assert raised.value.code == "unsupported_cli_field"
