from pathlib import Path


def test_bundled_skill_exposes_main_and_reference_files() -> None:
    from agent_surface.skills import bundled_skill_path

    with bundled_skill_path("agent-friendly-cli-design") as skill_dir:
        assert (skill_dir / "SKILL.md").is_file()
        assert (skill_dir / "reference.md").is_file()


def test_bundled_skill_does_not_ship_editor_state() -> None:
    from agent_surface.skills import bundled_skill_path

    with bundled_skill_path("agent-friendly-cli-design") as skill_dir:
        names = {path.name for path in Path(skill_dir).iterdir()}

    assert not any(name.endswith(".un~") for name in names)
