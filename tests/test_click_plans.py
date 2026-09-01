from enum import StrEnum
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, Field, StrictInt, create_model

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


def test_declarative_long_options_replace_the_derived_option_name() -> None:
    class AliasedRequest(BaseModel):
        plan_only: bool = Field(
            default=False,
            json_schema_extra={"cli": {"options": ["--plan", "--plan-only"]}},
        )
        apply_changes: bool = Field(
            default=False,
            json_schema_extra={"cli": {"options": ["--apply"]}},
        )

    fields = CliPlanCompiler(app_for(AliasedRequest).operations).compile()[0].fields

    assert fields[0].parameter_decls == ("--plan", "--plan-only")
    assert fields[1].parameter_decls == ("--apply",)


@pytest.mark.parametrize(
    "cli",
    [
        {"options": []},
        {"options": ["plan"]},
        {"options": ["--plan", "--plan"]},
        {"kind": "argument", "options": ["--plan"]},
        {"source": "stdin", "options": ["--plan"]},
    ],
)
def test_invalid_declarative_long_options_are_rejected(cli: dict[str, object]) -> None:
    class InvalidAliasRequest(BaseModel):
        plan_only: bool = Field(default=False, json_schema_extra={"cli": cli})

    with pytest.raises(CliDefinitionError) as raised:
        CliPlanCompiler(app_for(InvalidAliasRequest).operations).compile()

    assert raised.value.code == "cli_parameter_conflict"


def test_declarative_long_options_cannot_collide_between_fields() -> None:
    class CollidingAliasRequest(BaseModel):
        plan_only: bool = Field(
            default=False,
            json_schema_extra={"cli": {"options": ["--apply"]}},
        )
        apply_changes: bool = Field(
            default=False,
            json_schema_extra={"cli": {"options": ["--apply"]}},
        )

    with pytest.raises(CliDefinitionError) as raised:
        CliPlanCompiler(app_for(CollidingAliasRequest).operations).compile()

    assert raised.value.code == "cli_parameter_conflict"


def test_sensitive_string_field_can_be_projected_from_stdin() -> None:
    class StdinRequest(BaseModel):
        host: str
        bws_token: str = Field(
            min_length=1,
            json_schema_extra={
                "sensitive": True,
                "cli": {
                    "source": "stdin",
                    "max_bytes": 8_192,
                    "strip_trailing_newline": True,
                },
            },
        )

    fields = CliPlanCompiler(app_for(StdinRequest).operations).compile()[0].fields
    token = fields[1]

    assert token.source == "stdin"
    assert token.parameter_decls == ()
    assert token.stdin_flag == "--bws-token-stdin"
    assert token.stdin_max_bytes == 8_192
    assert token.strip_trailing_newline is True


@pytest.mark.parametrize(
    "request_model",
    [
        create_model(
            "InsecureStdinRequest",
            bws_token=(str, Field(json_schema_extra={"cli": {"source": "stdin"}})),
        ),
        create_model(
            "TwoStdinFieldsRequest",
            first=(
                str,
                Field(
                    json_schema_extra={"sensitive": True, "cli": {"source": "stdin"}}
                ),
            ),
            second=(
                str,
                Field(
                    json_schema_extra={"sensitive": True, "cli": {"source": "stdin"}}
                ),
            ),
        ),
    ],
)
def test_stdin_field_metadata_rejects_unsafe_or_ambiguous_shapes(
    request_model: type[BaseModel],
) -> None:
    with pytest.raises(CliDefinitionError) as raised:
        CliPlanCompiler(app_for(request_model).operations).compile()

    assert raised.value.code == "cli_parameter_conflict"


def test_stdin_presence_flag_cannot_collide_with_an_argv_option() -> None:
    class CollidingRequest(BaseModel):
        token: str = Field(
            json_schema_extra={"sensitive": True, "cli": {"source": "stdin"}}
        )
        token_stdin: str

    with pytest.raises(CliDefinitionError) as raised:
        CliPlanCompiler(app_for(CollidingRequest).operations).compile()

    assert raised.value.code == "cli_parameter_conflict"


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


@pytest.mark.parametrize("field_name", ["format", "yaml_style"])
def test_framework_render_option_names_fail_during_compilation(field_name: str) -> None:
    conflicting_request = type(
        "ConflictingRequest",
        (BaseModel,),
        {"__annotations__": {field_name: str}},
    )

    with pytest.raises(CliDefinitionError) as raised:
        CliPlanCompiler(app_for(conflicting_request).operations).compile()

    assert raised.value.code == "cli_parameter_conflict"


def test_destructive_confirm_field_must_be_boolean() -> None:
    class InvalidConfirmationRequest(BaseModel):
        target: str
        confirm: str

    app = App("danger")

    @app.operation("items.delete", destructive=True)
    def delete(request: InvalidConfirmationRequest) -> Result:
        return Result(status=request.target)

    with pytest.raises(CliDefinitionError) as raised:
        CliPlanCompiler(app.operations).compile()

    assert raised.value.code == "cli_parameter_conflict"


def test_required_optional_field_remains_required() -> None:
    class RequiredNullableRequest(BaseModel):
        value: str | None

    field = CliPlanCompiler(app_for(RequiredNullableRequest).operations).compile()[0].fields[0]

    assert field.required is True


def test_repeated_positional_field_is_rejected_as_lossy() -> None:
    class RepeatedArgumentRequest(BaseModel):
        values: list[str] = Field(json_schema_extra={"cli": {"kind": "argument"}})

    with pytest.raises(CliDefinitionError) as raised:
        CliPlanCompiler(app_for(RepeatedArgumentRequest).operations).compile()

    assert raised.value.code == "unsupported_cli_field"
