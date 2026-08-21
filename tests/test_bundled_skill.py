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


def test_agent_surface_authoring_reference_uses_actual_adapter_wiring() -> None:
    from agent_surface.skills import bundled_skill_path

    with bundled_skill_path("agent-surface-authoring") as skill_dir:
        reference = (skill_dir / "reference.md").read_text()

    assert "references = ReferenceRegistry()" in reference
    assert "references.register(WidgetRefCodec())" in reference
    assert "build_click_group(app, references=references)" in reference
    assert "MCPAdapter(app, references=references)" in reference
