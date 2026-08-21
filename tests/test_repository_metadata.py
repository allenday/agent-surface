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
    assert project["project"]["classifiers"] == [
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    ]


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
    assert "agent-surface[mcp]" in readme
    assert "from agent_surface import App" in readme
    assert "CONTRIBUTING.md" in readme


def test_readme_is_a_concise_human_first_hateoas_entry_point() -> None:
    readme = (ROOT / "README.md").read_text()
    normalized = readme.lower()

    for required in (
        "hateoas",
        "https://en.wikipedia.org/wiki/hateoas",
        "https://modelcontextprotocol.io/docs/getting-started/intro",
        "get up and running in 5 seconds",
        "agent-surface[mcp]",
        "from agent_surface import app",
        "next_actions",
        "./examples/bookstore",
        "src/agent_surface/skills/agent-friendly-cli-design/skill.md",
        "docs/tutorials/bookstore.md",
        "docs/concepts/hateoas.md",
        "docs/how-to/adopt-an-existing-app.md",
        "docs/reference/mcp-contract.md",
        "hello.py --mcp",
        'sys.argv[1:] == ["--mcp"]',
        "asyncio.run(mcp.run_stdio())",
        "~/.codex/config.toml",
        '"mcpservers"',
        "src/agent_surface/skills/install.sh | sh",
        "agent-surface-authoring",
        "agent-surface-authoring/skill.md",
    ):
        assert required in normalized
    old_hateoas_url = (
        "https://ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm#sec_5_2_3"
    )
    assert old_hateoas_url not in normalized
    assert "hello_mcp.py" not in normalized
    assert len(readme.splitlines()) <= 260

    promise = normalized.index("typed python operations that become")
    show_and_tell = normalized.index("class greetrequest")
    install_and_run = normalized.index("pip install 'agent-surface[mcp]'")
    mcp_configuration = normalized.index("~/.codex/config.toml")
    skill_installation = normalized.index("src/agent_surface/skills/install.sh | sh")
    assert promise < skill_installation < show_and_tell < install_and_run < mcp_configuration


def test_skill_installer_and_authoring_preflight_keep_environment_choices_with_the_user() -> None:
    installer = (ROOT / "src" / "agent_surface" / "skills" / "install.sh").read_text()
    skill = (
        ROOT / "src" / "agent_surface" / "skills" / "agent-surface-authoring" / "SKILL.md"
    ).read_text()

    assert installer.startswith("#!/bin/sh\nset -eu\n")
    assert "pip install" not in installer
    assert "Environment preflight" in skill
    assert "Do not choose or create a virtual environment" in skill
    assert "agent-surface[mcp]" in skill


def test_public_docs_present_mcp_as_a_shipped_sibling_adapter() -> None:
    readme = (ROOT / "README.md").read_text()
    tutorial = (ROOT / "docs" / "tutorials" / "bookstore.md").read_text()
    python_api = (ROOT / "docs" / "reference" / "python-api.md").read_text()
    mcp_contract = ROOT / "docs" / "reference" / "mcp-contract.md"

    assert "pip install 'agent-surface[mcp]'" in readme
    assert "MCPAdapter" in readme
    assert "docs/reference/mcp-contract.md" in readme
    assert "native MCP v2 and schema adapters are next" not in readme
    assert "operation" in tutorial and "bound" in tutorial
    assert "MCPAdapter" in python_api
    assert mcp_contract.is_file()
    contract = mcp_contract.read_text()
    for required in (
        "stdio",
        "Streamable HTTP",
        "structuredContent",
        "nextCursor",
        "confirmation",
        "annotations",
        "Click",
    ):
        assert required in contract


def test_bookstore_docs_cover_persistent_crud_and_local_mcp_clients() -> None:
    tutorial = (ROOT / "docs" / "tutorials" / "bookstore.md").read_text()

    assert (ROOT / "examples" / "bookstore-mcp").stat().st_mode & 0o111
    for required in (
        "examples/bookstore-mcp",
        "AGENT_SURFACE_BOOKSTORE_DB",
        "holds get",
        "holds cancel",
        "holds delete",
    ):
        assert required in tutorial
    for required in (
        "[mcp_servers.bookstore]",
        "codex mcp add bookstore",
        "claude mcp add --transport stdio --scope user",
        '"mcpServers"',
        "sqlite3",
        "standard library",
        "https://developers.openai.com/codex/mcp",
        "https://code.claude.com/docs/en/mcp",
        "${CLAUDE_PROJECT_DIR:-.}",
        r".venv\Scripts\python.exe",
    ):
        assert required in tutorial


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
    assert "docs/how-to/adopt-an-existing-app.md" in readme
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
    python_api = (ROOT / "docs" / "reference" / "python-api.md").read_text()
    mcp_contract = (ROOT / "docs" / "reference" / "mcp-contract.md").read_text()
    agent_guide = (ROOT / "AGENTS.md").read_text()

    assert "docs/reference/python-api.md" in readme
    assert "docs/reference/mcp-contract.md" in readme
    for required in (
        "RenderOptions",
        "BoundedCollection",
        "render_envelope",
    ):
        assert required in python_api
    assert "65,536" in mcp_contract
    for required in (
        "rendering.py",
        "never fabricate pagination",
        "never silently truncate",
    ):
        assert required in agent_guide


def test_bounded_action_discovery_contract_is_public_and_agent_enforced() -> None:
    readme = (ROOT / "README.md").read_text()
    references = (ROOT / "docs" / "how-to" / "references-and-actions.md").read_text()
    adoption = (ROOT / "docs" / "adoption.md").read_text()
    agent_guide = (ROOT / "AGENTS.md").read_text()

    assert "docs/how-to/references-and-actions.md" in readme
    for required in (
        "ReferenceCodec",
        "ReferenceRegistry",
        "ActionCatalog",
        "AllowActions",
        "@action",
        "immediate continuation",
    ):
        assert required in references
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
