import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_core_and_click_do_not_import_mcp() -> None:
    script = (
        "import agent_surface; import agent_surface.adapters.click; "
        "import sys; assert 'mcp' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_mcp_adapter_has_actionable_missing_extra_error() -> None:
    script = (
        "import sys; sys.modules['mcp']=None; "
        "import agent_surface.adapters.mcp"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "pip install 'agent-surface[mcp]'" in result.stderr


def test_mcp_extra_targets_v2_and_adapter_does_not_import_click() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)

    assert project["project"]["optional-dependencies"]["mcp"] == ["mcp>=2.0.0,<3"]

    adapter_source = (ROOT / "src/agent_surface/adapters/mcp.py").read_text()
    assert "agent_surface.adapters.click" not in adapter_source
    assert "import click" not in adapter_source

    script = "import agent_surface.adapters.mcp"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
