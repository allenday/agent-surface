import pytest
from pydantic import BaseModel

from agent_surface import App, ComposedApp
from agent_surface.manifest import (
    ManifestCollision,
    ManifestMismatch,
    manifest_for,
    validate_manifests,
    verify_manifest,
)


class Request(BaseModel):
    name: str


class Result(BaseModel):
    greeting: str


def app() -> App:
    value = App("fixture", version="1.2.3")

    @value.operation("greetings.hello", summary="Return a greeting", read_only=True)
    def hello(request: Request) -> Result:
        return Result(greeting=f"Hello {request.name}")

    return value


def test_manifest_is_deterministic_registry_data() -> None:
    document = manifest_for(
        app(),
        factory="fixture.surface:build_app",
        distribution_name="fixture-plugin",
        distribution_version="4.5.6",
    )

    assert document["schema_version"] == 1
    assert document["app"] == {"name": "fixture", "version": "1.2.3"}
    assert document["distribution"] == {"name": "fixture-plugin", "version": "4.5.6"}
    assert document["factory"] == "fixture.surface:build_app"
    operation = document["operations"][0]
    assert operation["path"] == ["greetings", "hello"]
    assert operation["summary"] == "Return a greeting"
    assert operation["annotations"] == {
        "read_only": True,
        "destructive": False,
        "idempotent": False,
        "open_world": False,
    }
    assert operation["input_schema"] == Request.model_json_schema(mode="validation")
    assert operation["output_schema"] == Result.model_json_schema(mode="serialization")


def test_manifest_verification_fails_closed_for_a_substituted_app() -> None:
    document = manifest_for(app(), factory="fixture.surface:build_app")
    substituted = App("fixture", version="1.2.3")

    @substituted.operation("greetings.goodbye")
    def goodbye(request: Request) -> Result:
        return Result(greeting=f"Bye {request.name}")

    with pytest.raises(ManifestMismatch):
        verify_manifest(substituted, document)


def test_composed_manifest_uses_public_paths_and_verifies() -> None:
    surface = ComposedApp("host", version="2.0.0").mount("catalog", app())
    document = manifest_for(surface, factory="fixture.surface:build_surface")

    assert document["operations"][0]["name"] == "catalog.greetings.hello"
    assert document["operations"][0]["path"] == ["catalog", "greetings", "hello"]
    verify_manifest(surface, document)


def test_manifest_collection_rejects_duplicate_operation_paths() -> None:
    document = manifest_for(app(), factory="fixture.surface:build_app")
    duplicate = manifest_for(app(), factory="other.surface:build_app")

    with pytest.raises(ManifestCollision, match="greetings hello"):
        validate_manifests([document, duplicate])


def test_manifest_collection_rejects_prefix_colliding_operation_paths() -> None:
    document = manifest_for(app(), factory="fixture.surface:build_app")
    prefix = manifest_for(app(), factory="other.surface:build_app")
    prefix["operations"][0]["name"] = "greetings"
    prefix["operations"][0]["path"] = ["greetings"]

    with pytest.raises(ManifestCollision, match="greetings hello"):
        validate_manifests([document, prefix])


def test_manifest_collection_requires_distribution_identity() -> None:
    document = manifest_for(app(), factory="fixture.surface:build_app")
    del document["distribution"]

    with pytest.raises(ManifestMismatch, match="distribution identity"):
        validate_manifests([document])


def test_manifest_collection_requires_complete_operation_contracts() -> None:
    document = manifest_for(app(), factory="fixture.surface:build_app")
    del document["operations"][0]["summary"]

    with pytest.raises(ManifestMismatch, match="invalid operation summary"):
        validate_manifests([document])
