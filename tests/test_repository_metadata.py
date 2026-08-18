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
