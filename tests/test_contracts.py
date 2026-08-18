import pytest
from pydantic import ValidationError

from agent_surface.contracts import (
    Action,
    ActionCollection,
    CommandView,
    ErrorEnvelope,
    ErrorInfo,
    ParsedCommand,
    SuccessEnvelope,
)


def command_view() -> CommandView:
    return CommandView(
        raw=("repo", "inspect", "my repo", "--details"),
        parsed=ParsedCommand(
            path=("repo", "inspect"),
            args={"repo": "my repo"},
            flags=("details",),
        ),
    )


def test_success_envelope_preserves_argv_and_dumps_for_yaml() -> None:
    envelope = SuccessEnvelope[dict[str, str]](
        command=command_view(),
        result={"status": "clean"},
    )

    assert envelope.ok is True
    assert envelope.command.raw == ("repo", "inspect", "my repo", "--details")
    assert envelope.model_dump(mode="json")["command"]["raw"] == [
        "repo",
        "inspect",
        "my repo",
        "--details",
    ]


def test_error_envelope_has_stable_repair_contract() -> None:
    envelope = ErrorEnvelope(
        command=command_view(),
        error=ErrorInfo(code="invalid_input", message="repo is required"),
        fix="Pass a repository reference.",
    )

    assert envelope.ok is False
    assert envelope.error.code == "invalid_input"
    assert envelope.fix == "Pass a repository reference."


def test_truncated_actions_require_discovery() -> None:
    with pytest.raises(ValidationError, match="discover"):
        ActionCollection(total=10, returned=1, truncated=True, items=(
            Action(rel="inspect", command=("repo", "inspect", "repo:1")),
        ))


def test_action_collection_counts_actual_items() -> None:
    with pytest.raises(ValidationError, match="returned"):
        ActionCollection(total=1, returned=0, items=(
            Action(rel="inspect", command=("repo", "inspect", "repo:1")),
        ))


def test_contracts_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra"):
        ParsedCommand(path=("repo",), unknown=True)
