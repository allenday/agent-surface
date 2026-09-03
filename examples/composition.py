"""Minimal executable composed Click and MCP surface."""

from pydantic import BaseModel

from agent_surface import App, ComposedApp
from agent_surface.adapters.click import build_click_group
from agent_surface.adapters.mcp import MCPAdapter


class DiagramRequest(BaseModel):
    name: str


class DiagramResult(BaseModel):
    value: str


class ProjectRequest(BaseModel):
    identifier: str


class ProjectResult(BaseModel):
    value: str


def build_surface() -> ComposedApp:
    diagram = App("diagram")
    project = App("project")

    @diagram.operation("render", read_only=True)
    def render(request: DiagramRequest) -> DiagramResult:
        return DiagramResult(value=request.name)

    @project.operation("inspect", read_only=True)
    def inspect(request: ProjectRequest) -> ProjectResult:
        return ProjectResult(value=request.identifier)

    return ComposedApp("infralink", version="0.2.0").mount(
        "diagram", diagram
    ).mount("project", project)


surface = build_surface()
cli = build_click_group(surface)
mcp = MCPAdapter(surface)
