from pathlib import Path

import pytest


@pytest.mark.parametrize("name", ["agent-friendly-cli-design", "agent-surface-authoring"])
def test_bundled_skill_exposes_main_and_reference_files(name: str) -> None:
    from agent_surface.skills import bundled_skill_path

    with bundled_skill_path(name) as skill_dir:
        assert (skill_dir / "SKILL.md").is_file()
        assert (skill_dir / "reference.md").is_file()


@pytest.mark.parametrize("name", ["agent-friendly-cli-design", "agent-surface-authoring"])
def test_bundled_skill_does_not_ship_editor_state(name: str) -> None:
    from agent_surface.skills import bundled_skill_path

    with bundled_skill_path(name) as skill_dir:
        names = {path.name for path in Path(skill_dir).iterdir()}

    assert not any(name.endswith(".un~") for name in names)
