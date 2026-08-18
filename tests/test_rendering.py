import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError, field_serializer
from ruamel.yaml import YAML

from agent_surface import (
    Action,
    BoundedCollection,
    CommandView,
    OutputBudget,
    OutputBudgetExceeded,
    ParsedCommand,
    SuccessEnvelope,
)
from agent_surface.rendering import RenderOptions, render, render_envelope

GOLDEN = Path(__file__).parent / "golden"


class Profile(BaseModel):
    model_config = ConfigDict(frozen=True)

    labels: dict[str, str]
    tags: tuple[str, ...]
    notes: str


class Payload(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    profile: Profile


class SerializedCollection(BaseModel):
    count: int

    @field_serializer("count")
    def serialize_count(self, value: int) -> list[int]:
        return list(range(value))


def payload() -> Payload:
    return Payload(
        name="café",
        profile=Profile(
            labels={"env": "prod", "region": "ap-southeast"},
            tags=("alpha", "βeta"),
            notes="first line\nsecond line",
        ),
    )


def load_yaml(document: str):
    return YAML(typ="safe").load(document)


def expected_value() -> dict[str, object]:
    return payload().model_dump(mode="json")


def command_view() -> CommandView:
    return CommandView(
        raw=("inventory", "resource", "list"),
        parsed=ParsedCommand(path=("resource", "list")),
    )


def test_render_options_default_to_yaml_auto_and_validate_literals() -> None:
    options = RenderOptions()

    assert options.format == "yaml"
    assert options.yaml_style == "auto"
    with pytest.raises(ValidationError):
        RenderOptions(format="toml")
    with pytest.raises(ValidationError):
        RenderOptions(yaml_style="columns")


@pytest.mark.parametrize("style", ["auto", "flow", "block"])
def test_yaml_styles_match_golden_files_and_round_trip(style: str) -> None:
    document = render(payload(), options=RenderOptions(yaml_style=style))

    assert document == (GOLDEN / f"render-{style}.yaml").read_text()
    assert load_yaml(document) == expected_value()


def test_auto_style_uses_flow_only_for_small_single_line_leaf_collections() -> None:
    document = render(
        {
            "small": [1, 2, 3],
            "large": [1, 2, 3, 4, 5, 6, 7],
            "wide": {"value": "x" * 101},
            "multiline": {"value": "one\ntwo"},
        }
    )

    assert "small: [1, 2, 3]" in document
    assert "large:\n- 1" in document
    assert "wide:\n  value:" in document
    assert "multiline:\n  value: |-" in document
    assert load_yaml(document)["multiline"] == {"value": "one\ntwo"}


def test_json_is_explicit_deterministic_unicode_output() -> None:
    document = render(payload(), options=RenderOptions(format="json"))

    assert "café" in document
    assert "βeta" in document
    assert document.index('"name"') < document.index('"profile"')
    assert json.loads(document) == expected_value()


def test_render_rejects_unmarked_sequence_over_item_budget_at_precise_path() -> None:
    options = RenderOptions(budget=OutputBudget(max_items=2))

    with pytest.raises(OutputBudgetExceeded) as raised:
        render({"result": {"items": ["one", "two", "three"]}}, options=options)

    assert raised.value.code == "item_budget_exceeded"
    assert raised.value.path == ("result", "items")
    assert raised.value.details == {"returned": 3, "max_items": 2}


@pytest.mark.parametrize(
    ("value", "expected_path"),
    [
        ({"result": ["one", "two", "three"]}, ("result",)),
        (
            {"result": {"records": ["one", "two", "three"]}},
            ("result", "records"),
        ),
    ],
)
def test_render_budgets_nested_sequences_independent_of_field_name(
    value: dict[str, object],
    expected_path: tuple[str, ...],
) -> None:
    with pytest.raises(OutputBudgetExceeded) as raised:
        render(value, options=RenderOptions(budget=OutputBudget(max_items=2)))

    assert raised.value.code == "item_budget_exceeded"
    assert raised.value.path == expected_path


def test_typed_command_structure_does_not_consume_domain_item_budget() -> None:
    envelope = SuccessEnvelope[str](
        command=CommandView(
            raw=("inventory", "resource", "inspect", "resource-1"),
            parsed=ParsedCommand(
                path=("resource", "inspect"),
                flags=("verbose", "resolved"),
            ),
        ),
        result="ok",
    )

    document = render(envelope, options=RenderOptions(budget=OutputBudget(max_items=1)))

    assert load_yaml(document)["result"] == "ok"


def test_render_budgets_collections_created_by_pydantic_serializers() -> None:
    with pytest.raises(OutputBudgetExceeded) as raised:
        render(
            SerializedCollection(count=3),
            options=RenderOptions(budget=OutputBudget(max_items=2)),
        )

    assert raised.value.path == ("count",)


@pytest.mark.parametrize(
    "value",
    [
        ParsedCommand(path=("inspect",), args={"refs": ["one", "two", "three"]}),
        Action(
            rel="inspect",
            command=("inventory", "inspect"),
            target={"refs": ["one", "two", "three"]},
        ),
    ],
)
def test_structural_contracts_exempt_only_their_argv_sequences(value: object) -> None:
    with pytest.raises(OutputBudgetExceeded) as raised:
        render(value, options=RenderOptions(budget=OutputBudget(max_items=2)))

    assert raised.value.code == "item_budget_exceeded"


def test_explicit_bounded_collection_renders_without_ellipsis_placeholder() -> None:
    collection = BoundedCollection[str].from_sequence(
        ("one", "two", "three"),
        budget=OutputBudget(max_items=2),
        continuation=Action(
            rel="next-page",
            command=("inventory", "list", "--cursor", "two"),
        ),
    )

    document = render(collection, options=RenderOptions(budget=OutputBudget(max_items=2)))
    parsed = load_yaml(document)

    assert parsed["items"] == ["one", "two"]
    assert parsed["total"] == 3
    assert parsed["truncated"] is True
    assert "..." not in document
    assert "..." not in parsed["items"]


def test_render_enforces_exact_utf8_byte_boundary() -> None:
    value = {"message": "สวัสดี"}
    unconstrained = render(value)
    measured = len(unconstrained.encode("utf-8"))

    exact = render(
        value,
        options=RenderOptions(budget=OutputBudget(max_bytes=measured)),
    )
    assert exact == unconstrained

    with pytest.raises(OutputBudgetExceeded) as raised:
        render(
            value,
            options=RenderOptions(budget=OutputBudget(max_bytes=measured - 1)),
        )
    assert raised.value.code == "response_too_large"
    assert raised.value.path == ()
    assert raised.value.details == {
        "measured_bytes": measured,
        "max_bytes": measured - 1,
    }


def test_render_envelope_substitutes_complete_structured_size_error() -> None:
    envelope = SuccessEnvelope[dict[str, str]](
        command=command_view(),
        result={"payload": "x" * 5_000},
    )
    options = RenderOptions(budget=OutputBudget(max_bytes=800))

    document = render_envelope(envelope, options=options)
    parsed = load_yaml(document)

    assert len(document.encode("utf-8")) <= 800
    assert parsed["ok"] is False
    assert parsed["command"]["raw"] == ["inventory", "resource", "list"]
    assert parsed["error"]["code"] == "response_too_large"
    assert parsed["error"]["details"][0]["code"] == "response_too_large"
    assert parsed["error"]["details"][0]["value"]["measured_bytes"] > 800
    assert parsed["error"]["details"][0]["value"]["max_bytes"] == 800
    assert parsed["fix"] == "Retry with a lower item limit or a narrower detail level."
    assert "result" not in parsed


def test_render_envelope_reraises_original_error_when_fallback_cannot_fit() -> None:
    envelope = SuccessEnvelope[dict[str, str]](
        command=command_view(),
        result={"payload": "x" * 5_000},
    )

    with pytest.raises(OutputBudgetExceeded) as raised:
        render_envelope(
            envelope,
            options=RenderOptions(budget=OutputBudget(max_bytes=1)),
        )

    assert raised.value.code == "response_too_large"
    assert raised.value.details["max_bytes"] == 1
    assert raised.value.details["measured_bytes"] > 1
