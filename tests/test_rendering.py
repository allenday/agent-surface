import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from ruamel.yaml import YAML

from agent_surface import Action, BoundedCollection, OutputBudget, OutputBudgetExceeded
from agent_surface.rendering import RenderOptions, render

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
