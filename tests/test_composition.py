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


def test_composed_app_copies_immutable_options_for_each_route() -> None:
    surface = ComposedApp("infralink").mount(
        "diagram",
        child("render", "render"),
        output="yaml",
    )
    second = surface.mount("project", child("project", "run"), output="json")

    first_route, second_route = second.operations()

    with pytest.raises(TypeError):
        first_route.options["output"] = "json"  # type: ignore[index]
    assert first_route.options is not second_route.options
    assert first_route.options == {"output": "yaml"}
    assert second_route.options == {"output": "json"}


@pytest.mark.parametrize("operation", ["", "render.", "render..detail"])
def test_composed_app_rejects_malformed_child_operation_paths(operation: str) -> None:
    with pytest.raises(CompositionError, match="non-empty path segments"):
        ComposedApp("infralink").mount("diagram", child("render", operation))
