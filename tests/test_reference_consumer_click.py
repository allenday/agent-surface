import json
from pathlib import Path

from click.testing import CliRunner

from agent_surface.adapters.click import ClickAdapter
from tests.reference_consumer.integration import build_app, build_references


def invoke(command, args: list[str]):
    result = CliRunner().invoke(command, [*args, "--format", "json"])
    return result, json.loads(result.stdout)


def test_reference_consumer_lookup_matches_direct_invocation() -> None:
    app, _catalog = build_app()
    command = ClickAdapter(app, references=build_references()).command()

    result, document = invoke(command, ["resource", "lookup", "--ref", "resource-a"])

    assert result.exit_code == 0
    assert document["result"] == {
        "ref": {"value": "resource-a"},
        "label": "Alpha",
        "revision": 1,
    }


def test_reference_consumer_async_page_runs_without_transport_logic() -> None:
    app, _catalog = build_app()
    command = ClickAdapter(app, references=build_references()).command()

    result, document = invoke(command, ["resource", "list", "--limit", "1"])

    assert result.exit_code == 0
    assert document["result"]["returned"] == 1
    assert document["result"]["truncated"] is True
    assert document["result"]["next_cursor"] == "resource-a"


def test_reference_consumer_domain_error_keeps_stable_semantics() -> None:
    app, _catalog = build_app()
    command = ClickAdapter(app, references=build_references()).command()

    result, document = invoke(command, ["resource", "lookup", "--ref", "missing"])

    assert result.exit_code == 4
    assert document["error"]["code"] == "resource_not_found"
    assert document["fix"] == "Choose a reference returned by resource.list"


def test_reference_consumer_mutation_uses_adapter_confirmation_gate() -> None:
    app, _catalog = build_app()
    command = ClickAdapter(app, references=build_references()).command()

    denied, denied_document = invoke(
        command,
        ["resource", "mutate", "--ref", "resource-a", "--access-token", "secret"],
    )
    allowed, allowed_document = invoke(
        command,
        [
            "resource",
            "mutate",
            "--ref",
            "resource-a",
            "--access-token",
            "secret",
            "--confirm",
        ],
    )

    assert denied.exit_code == 3
    assert denied_document["error"]["code"] == "confirmation_required"
    assert allowed.exit_code == 0
    assert allowed_document["result"]["changed"] is True
    assert "secret" not in allowed.output


def test_consumer_domain_remains_transport_free() -> None:
    text = Path("tests/reference_consumer/domain.py").read_text()

    assert "click" not in text
    assert "mcp" not in text
    assert "agent_surface.adapters" not in text
