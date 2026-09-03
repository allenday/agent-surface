"""Import-free, deterministic operation manifests for installed plugin wheels."""

import json
import re
from collections.abc import Mapping, Sequence
from importlib import import_module, metadata
from pathlib import Path
from typing import Any

from agent_surface.app import App
from agent_surface.composition import ComposedApp

MANIFEST_FILENAME = "agent-surface-operations.json"


class ManifestMismatch(ValueError):
    """An imported application no longer matches its selected manifest."""


class ManifestCollision(ValueError):
    """Installed manifests cannot be mounted into one unambiguous command tree."""


def manifest_for(
    app: App | ComposedApp,
    *,
    factory: str,
    distribution_name: str | None = None,
    distribution_version: str | None = None,
) -> dict[str, Any]:
    """Derive a stable JSON-compatible manifest from one registered application."""
    operations = []
    if isinstance(app, ComposedApp):
        for route in app.operations():
            definition = route.operation
            operations.append(
                {
                    "name": route.public_name,
                    "path": list(route.public_path),
                    "summary": definition.summary,
                    "annotations": {
                        "read_only": definition.read_only,
                        "destructive": definition.destructive,
                        "idempotent": definition.idempotent,
                        "open_world": definition.open_world,
                    },
                    "input_schema": definition.input_model.model_json_schema(mode="validation"),
                    "output_schema": definition.output_model.model_json_schema(
                        mode="serialization"
                    ),
                    "source": {
                        "app": {"name": route.app.name, "version": route.app.version},
                        "operation": definition.name,
                    },
                }
            )
    else:
        for definition in app.operations.list():
            operations.append(
                {
                    "name": definition.name,
                    "path": definition.name.split("."),
                "summary": definition.summary,
                "annotations": {
                    "read_only": definition.read_only,
                    "destructive": definition.destructive,
                    "idempotent": definition.idempotent,
                    "open_world": definition.open_world,
                },
                "input_schema": definition.input_model.model_json_schema(mode="validation"),
                "output_schema": definition.output_model.model_json_schema(mode="serialization"),
                }
            )
    return {
        "schema_version": 1,
        "app": {"name": app.name, "version": app.version},
        "distribution": {
            "name": distribution_name or app.name,
            "version": distribution_version or app.version,
        },
        "factory": factory,
        "operations": operations,
    }


def write_manifest(
    app: App | ComposedApp,
    path: Path,
    *,
    factory: str,
    distribution_name: str | None = None,
    distribution_version: str | None = None,
) -> None:
    """Write canonical UTF-8 JSON suitable for inclusion in a wheel."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            manifest_for(
                app,
                factory=factory,
                distribution_name=distribution_name,
                distribution_version=distribution_version,
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def generate_manifest(
    factory: str,
    path: Path,
    *,
    distribution_name: str | None = None,
    distribution_version: str | None = None,
) -> None:
    """Import one explicit build-time factory and write its manifest artifact."""
    module_name, separator, attribute = factory.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("factory must use the form package.module:attribute")
    value = getattr(import_module(module_name), attribute)
    app = value() if callable(value) else value
    if not isinstance(app, (App, ComposedApp)):
        raise TypeError("manifest factory must resolve to an App or ComposedApp")
    write_manifest(
        app,
        path,
        factory=factory,
        distribution_name=distribution_name,
        distribution_version=distribution_version,
    )


def load_manifest(path: Path) -> dict[str, Any]:
    """Read a manifest file without importing any plugin package."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ManifestMismatch("Unsupported operation manifest")
    validate_manifests([value])
    return value


def installed_manifests() -> tuple[dict[str, Any], ...]:
    """Read installed manifests without importing any third-party application code."""
    manifests: list[dict[str, Any]] = []
    for distribution in metadata.distributions():
        for file in distribution.files or ():
            if file.name == MANIFEST_FILENAME and any(
                part.endswith(".dist-info") for part in file.parts
            ):
                manifest = load_manifest(Path(str(distribution.locate_file(file))))
                _validate_distribution_identity(
                    manifest, distribution.metadata["Name"], distribution.version
                )
                manifests.append(manifest)
    validate_manifests(manifests)
    return tuple(sorted(manifests, key=_manifest_sort_key))


def validate_manifests(manifests: Sequence[Mapping[str, Any]]) -> None:
    """Reject duplicate and prefix-colliding command paths deterministically."""
    paths: list[tuple[str, ...]] = []
    for manifest in manifests:
        _manifest_identity(manifest, "app")
        _manifest_identity(manifest, "distribution")
        factory = manifest.get("factory")
        if not isinstance(factory, str) or not factory:
            raise ManifestMismatch("Operation manifest has an invalid factory")
        operations = manifest.get("operations")
        if not isinstance(operations, list):
            raise ManifestMismatch("Operation manifest has no operations list")
        for operation in operations:
            if not isinstance(operation, Mapping):
                raise ManifestMismatch("Operation manifest contains an invalid operation")
            name = operation.get("name")
            if not isinstance(name, str) or not name:
                raise ManifestMismatch("Operation manifest contains an invalid operation name")
            path = operation.get("path")
            if not isinstance(path, list) or not path or not all(
                isinstance(token, str) and token for token in path
            ):
                raise ManifestMismatch("Operation manifest contains an invalid operation path")
            operation_path = tuple(path)
            if operation_path != tuple(name.split(".")):
                raise ManifestMismatch("Operation manifest path does not match its operation name")
            if not isinstance(operation.get("summary"), str):
                raise ManifestMismatch("Operation manifest contains an invalid operation summary")
            annotations = operation.get("annotations")
            expected_annotations = {"read_only", "destructive", "idempotent", "open_world"}
            annotations_are_valid = isinstance(annotations, Mapping) and set(annotations) == (
                expected_annotations
            ) and all(isinstance(annotations[key], bool) for key in expected_annotations)
            if not annotations_are_valid:
                raise ManifestMismatch("Operation manifest contains invalid operation annotations")
            if not isinstance(operation.get("input_schema"), Mapping) or not isinstance(
                operation.get("output_schema"), Mapping
            ):
                raise ManifestMismatch("Operation manifest contains invalid JSON Schemas")
            source = operation.get("source")
            if source is not None:
                source_app = source.get("app") if isinstance(source, Mapping) else None
                if (
                    not isinstance(source_app, Mapping)
                    or not isinstance(source_app.get("name"), str)
                    or not isinstance(source_app.get("version"), str)
                    or not isinstance(source.get("operation"), str)
                ):
                    raise ManifestMismatch("Operation manifest contains invalid source provenance")
            paths.append(operation_path)

    sorted_paths = sorted(paths)
    for index, path in enumerate(sorted_paths):
        if index and _paths_collide(sorted_paths[index - 1], path):
            raise ManifestCollision(f"Operation path collision: {' '.join(path)}")


def verify_manifest(app: App | ComposedApp, manifest: Mapping[str, Any]) -> None:
    """Fail closed unless an explicitly imported app exactly matches its artifact."""
    factory = manifest.get("factory")
    distribution = manifest.get("distribution")
    if (
        not isinstance(factory, str)
        or not isinstance(distribution, Mapping)
        or not isinstance(distribution.get("name"), str)
        or not isinstance(distribution.get("version"), str)
        or manifest_for(
            app,
            factory=factory,
            distribution_name=distribution["name"],
            distribution_version=distribution["version"],
        )
        != dict(manifest)
    ):
        raise ManifestMismatch("Installed application does not match its operation manifest")


def _manifest_sort_key(manifest: Mapping[str, Any]) -> tuple[str, str]:
    name, version = _manifest_identity(manifest, "app")
    return name, version


def _manifest_identity(manifest: Mapping[str, Any], key: str) -> tuple[str, str]:
    identity = manifest.get(key)
    if not isinstance(identity, Mapping):
        raise ManifestMismatch(f"Operation manifest has no {key} identity")
    name = identity.get("name")
    version = identity.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        raise ManifestMismatch(f"Operation manifest has an invalid {key} identity")
    return name, version


def _validate_distribution_identity(
    manifest: Mapping[str, Any], distribution_name: str, distribution_version: str
) -> None:
    name, version = _manifest_identity(manifest, "distribution")
    if _normalized_distribution_name(name) != _normalized_distribution_name(distribution_name) or (
        version != distribution_version
    ):
        raise ManifestMismatch("Operation manifest distribution identity does not match its wheel")


def _normalized_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _paths_collide(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return left == right or left == right[: len(left)]


__all__ = [
    "MANIFEST_FILENAME",
    "ManifestCollision",
    "ManifestMismatch",
    "generate_manifest",
    "load_manifest",
    "manifest_for",
    "installed_manifests",
    "validate_manifests",
    "verify_manifest",
    "write_manifest",
]
