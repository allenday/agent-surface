import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_python_tooling_uses_the_declared_minimum_version() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)

    assert project["project"]["requires-python"] == ">=3.12"
    assert project["tool"]["ruff"]["target-version"] == "py312"
    assert project["tool"]["mypy"]["python_version"] == "3.12"


def test_project_metadata_points_to_its_public_repository() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)

    urls = project["project"]["urls"]
    assert urls["Repository"] == "https://github.com/allenday/agent-surface"
    assert urls["Issues"] == "https://github.com/allenday/agent-surface/issues"


def test_makefile_exposes_one_complete_check_command() -> None:
    makefile = (ROOT / "Makefile").read_text()

    assert "check:" in makefile
    assert "pytest" in makefile
    assert "ruff check" in makefile
    assert "mypy" in makefile
    assert "uv build" in makefile


def test_readme_orients_users_and_contributors() -> None:
    readme = (ROOT / "README.md").read_text()

    assert "actions/workflows/ci.yml/badge.svg" in readme
    assert "pypi/v/agent-surface.svg" in readme
    assert "pip install agent-surface" in readme
    assert "from agent_surface import App" in readme
    assert "CONTRIBUTING.md" in readme


def test_agent_guide_contains_executable_repository_contract() -> None:
    guide = (ROOT / "AGENTS.md").read_text()

    for required in (
        "uv sync --frozen --all-extras --dev",
        "make check",
        "Python 3.12",
        "YAML",
        "Pydantic",
        "next_actions",
        "SKILL.md",
    ):
        assert required in guide


def test_public_project_sidecars_exist() -> None:
    for path in (
        "CONTRIBUTING.md",
        "SECURITY.md",
        "LICENSE",
        "docs/releasing.md",
    ):
        assert (ROOT / path).is_file(), path

    release_guide = (ROOT / "docs/releasing.md").read_text()
    for required in (
        "allenday",
        "agent-surface",
        "release.yml",
        "testpypi",
        "pypi",
        "Trusted Publisher",
    ):
        assert required in release_guide
