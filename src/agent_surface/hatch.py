"""Hatch build hook for packaging an application's operation manifest."""

import re
import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.plugin import hookimpl

from agent_surface.manifest import MANIFEST_FILENAME, generate_manifest


def manifest_destination(project_name: str, version: str) -> str:
    """Return the wheel metadata path for one project's manifest."""
    normalized_name = re.sub(r"[-_.]+", "_", project_name)
    return f"{normalized_name}-{version}.dist-info/{MANIFEST_FILENAME}"


class ManifestBuildHook(BuildHookInterface[Any]):
    """Generate one manifest by importing only the configured factory at build time."""

    PLUGIN_NAME = "agent-surface"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        factory = self.config.get("factory")
        if not isinstance(factory, str) or not factory:
            raise ValueError("agent-surface Hatch hook requires a non-empty 'factory' setting")

        source_paths = self.config.get("source", [".", "src"])
        if isinstance(source_paths, str):
            source_paths = [source_paths]
        if not isinstance(source_paths, list) or not all(
            isinstance(path, str) and path for path in source_paths
        ):
            raise ValueError("agent-surface Hatch hook setting 'source' must be a string or list")

        for source_path in reversed(source_paths):
            resolved = str(Path(self.root, source_path))
            if resolved not in sys.path:
                sys.path.insert(0, resolved)

        artifact = Path(self.directory, "agent-surface", MANIFEST_FILENAME)
        generate_manifest(
            factory,
            artifact,
            distribution_name=self.metadata.core.name,
            distribution_version=self.metadata.core.version,
        )
        build_data.setdefault("force_include", {})[str(artifact)] = manifest_destination(
            self.metadata.core.name, self.metadata.core.version
        )


@hookimpl
def hatch_register_build_hook() -> type[ManifestBuildHook]:
    """Register the externally-configured Hatch build hook."""
    return ManifestBuildHook


__all__ = ["ManifestBuildHook", "manifest_destination"]
