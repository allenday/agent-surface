import pytest
from pydantic import BaseModel

from agent_surface import App
from agent_surface.composition import ComposedApp, CompositionError


class Request(BaseModel):
    value: str


class Result(BaseModel):
    value: str


def child(name: str, operation: str) -> App:
    app = App(name)

    @app.operation(operation)
    def handle(request: Request) -> Result:
        return Result(value=request.value)

    return app


def test_composed_app_prefixes_child_operation_paths() -> None:
    surface = (
        ComposedApp("infralink")
        .mount("diagram", child("render", "render"))
        .mount(("diagram", "project"), child("project", "run"))
    )

    assert [route.public_name for route in surface.operations()] == [
        "diagram.project.run",
        "diagram.render",
    ]
    assert [route.operation.name for route in surface.operations()] == ["run", "render"]


def test_composed_app_rejects_duplicate_and_prefix_collisions() -> None:
    surface = ComposedApp("infralink").mount("diagram", child("render", "render"))

    with pytest.raises(CompositionError, match="Duplicate composed operation path"):
        surface.mount("diagram", child("other", "render"))

    with pytest.raises(CompositionError, match="Composed operation path collision"):
        (
            ComposedApp("infralink")
            .mount("diagram", child("leaf", "project"))
            .mount(("diagram", "project"), child("nested", "run"))
        )
