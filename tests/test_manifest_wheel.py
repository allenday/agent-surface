import subprocess
import textwrap
import venv
import zipfile
from pathlib import Path


def test_hatch_builds_and_installs_a_verifiable_manifest(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[1]
    package_root = tmp_path / "demo-ops"
    source_root = package_root / "src" / "demo_ops"
    source_root.mkdir(parents=True)
    (source_root / "__init__.py").touch()
    (source_root / "surface.py").write_text(
        textwrap.dedent(
            """
            from agent_surface import App
            from pydantic import BaseModel

            class Request(BaseModel):
                name: str

            class Result(BaseModel):
                greeting: str

            def build_app() -> App:
                app = App("demo-ops", version="1.0.0")

                @app.operation("greetings.hello", summary="Return a greeting", read_only=True)
                def hello(request: Request) -> Result:
                    return Result(greeting=f"Hello {request.name}")

                return app
            """
        ),
        encoding="utf-8",
    )
    (package_root / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""
            [build-system]
            requires = ["hatchling>=1.32.0", "agent-surface @ {project_root.as_uri()}"]
            build-backend = "hatchling.build"

            [project]
            name = "demo-ops"
            version = "1.0.0"
            dependencies = ["agent-surface"]

            [tool.hatch.build.targets.wheel]
            packages = ["src/demo_ops"]

            [tool.hatch.build.hooks.agent-surface]
            factory = "demo_ops.surface:build_app"
            """
        ),
        encoding="utf-8",
    )

    artifact_directory = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(artifact_directory), str(project_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "uv",
            "build",
            "--refresh",
            "--wheel",
            "--out-dir",
            str(artifact_directory),
            str(package_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(artifact_directory.glob("demo_ops-1.0.0-*.whl"))
    agent_surface_wheel = next(artifact_directory.glob("agent_surface-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert "demo_ops-1.0.0.dist-info/agent-surface-operations.json" in archive.namelist()

    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / "bin" / "python"
    subprocess.run(
        [str(python), "-m", "pip", "install", str(agent_surface_wheel), str(wheel)],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [
            str(python),
            "-c",
            (
                "from agent_surface import installed_manifests, verify_manifest; "
                "from demo_ops.surface import build_app; "
                "manifest = next(item for item in installed_manifests() "
                "if item['app']['name'] == 'demo-ops'); "
                "verify_manifest(build_app(), manifest)"
            ),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
