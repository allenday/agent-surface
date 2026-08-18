import re
import tomllib
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).parents[1]


def load_yaml(path: str) -> object:
    return YAML(typ="safe").load(ROOT / path)


def workflow_uses(workflow: dict[str, object]) -> list[str]:
    return [
        step["uses"]
        for job in workflow["jobs"].values()
        for step in job.get("steps", ())
        if "uses" in step
    ]


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


def test_readme_teaches_a_complete_hateoas_trajectory() -> None:
    readme = (ROOT / "README.md").read_text()
    normalized = readme.lower()

    for required in (
        "hateoas",
        "five-minute",
        "books search --query dune",
        "books inspect --book book_dune",
        "holds create --book book_dune --confirm",
        "next_actions",
        "docs/tutorials/bookstore.md",
        "docs/concepts/hateoas.md",
        "docs/how-to/adopt-an-existing-app.md",
        "docs/reference/cli-contract.md",
        "docs/reference/python-api.md",
    ):
        assert required in normalized


def test_critical_directories_have_scoped_agent_instructions() -> None:
    for path in (
        "src/agent_surface/AGENTS.md",
        "src/agent_surface/adapters/AGENTS.md",
        "src/agent_surface/skills/AGENTS.md",
        "tests/AGENTS.md",
        "examples/AGENTS.md",
        "docs/AGENTS.md",
        ".github/AGENTS.md",
    ):
        assert (ROOT / path).is_file(), path


def test_public_markdown_internal_links_resolve() -> None:
    documents = [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
    pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")

    for document in documents:
        for target in pattern.findall(document.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            relative = target.split("#", 1)[0]
            assert (document.parent / relative).resolve().exists(), f"{document}: {target}"


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


def test_adoption_boundary_is_documented_and_linked() -> None:
    guide_path = ROOT / "docs" / "adoption.md"
    assert guide_path.is_file()

    guide = guide_path.read_text()
    readme = (ROOT / "README.md").read_text()
    agent_guide = (ROOT / "AGENTS.md").read_text()
    assert "docs/adoption.md" in readme
    assert "docs/adoption.md" in agent_guide
    for required in (
        "consumer-owned",
        "integration layer",
        "OperationError",
        "shipped Click",
        "sensitive",
        "transport",
    ):
        assert required in guide


def test_bounded_rendering_contract_is_public_and_agent_enforced() -> None:
    readme = (ROOT / "README.md").read_text()
    agent_guide = (ROOT / "AGENTS.md").read_text()

    for required in (
        "RenderOptions",
        "BoundedCollection",
        "render_envelope",
        'yaml_style="flow"',
        'format="json"',
        "65,536",
    ):
        assert required in readme
    for required in (
        "rendering.py",
        "never fabricate pagination",
        "never silently truncate",
    ):
        assert required in agent_guide


def test_bounded_action_discovery_contract_is_public_and_agent_enforced() -> None:
    readme = (ROOT / "README.md").read_text()
    adoption = (ROOT / "docs" / "adoption.md").read_text()
    agent_guide = (ROOT / "AGENTS.md").read_text()

    for required in (
        "ReferenceCodec",
        "ReferenceRegistry",
        "ActionCatalog",
        "AllowActions",
        "@action",
        "immediate continuation",
    ):
        assert required in readme
    for required in (
        "exact-name",
        "explicit policy",
        "str(object)",
        "descriptor",
    ):
        assert required in adoption
    for required in (
        "properties or descriptors",
        "deny-by-default",
        "exhaustive action",
    ):
        assert required in agent_guide


def test_github_contributor_templates_are_structured_and_parseable() -> None:
    bug = load_yaml(".github/ISSUE_TEMPLATE/bug.yml")
    feature = load_yaml(".github/ISSUE_TEMPLATE/feature.yml")
    config = load_yaml(".github/ISSUE_TEMPLATE/config.yml")

    assert bug["name"] == "Bug report"
    assert {item.get("id") for item in bug["body"]} >= {"description", "reproduction"}
    assert feature["name"] == "Feature request"
    assert {item.get("id") for item in feature["body"]} >= {"problem", "proposal"}
    assert config["blank_issues_enabled"] is False

    pull_request = (ROOT / ".github/pull_request_template.md").read_text()
    assert "make check" in pull_request
    assert "Tests" in pull_request


def test_dependabot_tracks_uv_and_actions_weekly() -> None:
    dependabot = load_yaml(".github/dependabot.yml")
    updates = dependabot["updates"]

    assert {update["package-ecosystem"] for update in updates} == {"uv", "github-actions"}
    assert all(update["schedule"]["interval"] == "weekly" for update in updates)


def test_ci_covers_supported_python_and_builds_distributions() -> None:
    workflow = load_yaml(".github/workflows/ci.yml")

    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["on"]) == {"push", "pull_request"}
    assert workflow["jobs"]["test"]["strategy"]["matrix"]["python-version"] == [
        "3.12",
        "3.13",
        "3.14",
    ]
    quality_steps = workflow["jobs"]["quality"]["steps"]
    quality_commands = "\n".join(step.get("run", "") for step in quality_steps)
    assert "ruff check" in quality_commands
    assert "mypy src" in quality_commands
    assert "uv build" in quality_commands
    assert "dist/*.whl" in quality_commands

    test_uv = next(
        step for step in workflow["jobs"]["test"]["steps"] if step["name"] == "Set up uv"
    )
    quality_uv = next(
        step for step in workflow["jobs"]["quality"]["steps"] if step["name"] == "Set up uv"
    )
    assert test_uv["with"]["cache-suffix"] == "${{ matrix.python-version }}"
    assert quality_uv["with"]["cache-suffix"] == "quality"


def test_release_uses_separate_oidc_environments_and_one_build() -> None:
    workflow = load_yaml(".github/workflows/release.yml")

    assert set(workflow["on"]) == {"workflow_dispatch", "release"}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["publish-testpypi"]["environment"]["name"] == "testpypi"
    assert workflow["jobs"]["publish-pypi"]["environment"]["name"] == "pypi"
    assert workflow["jobs"]["publish-testpypi"]["permissions"] == {"id-token": "write"}
    assert workflow["jobs"]["publish-pypi"]["permissions"] == {"id-token": "write"}
    assert workflow["jobs"]["publish-testpypi"]["needs"] == "build"
    assert workflow["jobs"]["publish-pypi"]["needs"] == "build"

    source = (ROOT / ".github/workflows/release.yml").read_text()
    assert "make check" in source
    assert "GITHUB_REF_NAME" in source
    assert "pyproject.toml" in source
    assert "repository-url: https://test.pypi.org/legacy/" in source
    assert "password:" not in source


def test_actions_are_pinned_to_immutable_commits() -> None:
    workflows = [
        load_yaml(".github/workflows/ci.yml"),
        load_yaml(".github/workflows/release.yml"),
    ]

    uses = [reference for workflow in workflows for reference in workflow_uses(workflow)]
    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference) for reference in uses)
