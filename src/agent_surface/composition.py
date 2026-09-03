"""Transport-neutral composition of independently typed application surfaces."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from agent_surface.app import App
from agent_surface.operations import OperationDefinition


class CompositionError(ValueError):
    """Mounted applications cannot form one unambiguous public operation tree."""


@dataclass(frozen=True, slots=True)
class MountedOperation:
    """One child operation at its deterministic public path."""

    public_path: tuple[str, ...]
    app: App
    operation: OperationDefinition
    options: Mapping[str, Any]

    @property
    def public_name(self) -> str:
        return ".".join(self.public_path)


class ComposedApp:
    """Build one public operation namespace from independently typed Apps."""

    def __init__(self, name: str, *, version: str = "0.1.0") -> None:
        self.name = name
        self.version = version
        self._routes: list[MountedOperation] = []

    def mount(
        self,
        prefix: str | tuple[str, ...],
        app: App,
        **options: Any,
    ) -> "ComposedApp":
        segments = _prefix_segments(prefix)
        candidates = [
            MountedOperation(
                public_path=(*segments, *_operation_segments(definition.name)),
                app=app,
                operation=definition,
                options=MappingProxyType(dict(options)),
            )
            for definition in app.operations.list()
        ]
        _validate_routes((*self._routes, *candidates))
        self._routes.extend(candidates)
        return self

    def operations(self) -> tuple[MountedOperation, ...]:
        return tuple(sorted(self._routes, key=lambda route: route.public_path))


def _prefix_segments(prefix: str | tuple[str, ...]) -> tuple[str, ...]:
    segments = tuple(prefix.split(".")) if isinstance(prefix, str) else prefix
    if not segments or any(not isinstance(segment, str) or not segment for segment in segments):
        raise CompositionError("Mount prefix must contain non-empty path segments")
    return segments


def _operation_segments(name: str) -> tuple[str, ...]:
    segments = tuple(name.split("."))
    if not segments or any(not segment for segment in segments):
        raise CompositionError("Child operation path must contain non-empty path segments")
    return segments


def _validate_routes(routes: tuple[MountedOperation, ...]) -> None:
    ordered = sorted(routes, key=lambda route: route.public_path)
    for left, right in zip(ordered, ordered[1:], strict=False):
        if left.public_path == right.public_path:
            raise CompositionError(f"Duplicate composed operation path: {left.public_name}")
        if left.public_path == right.public_path[: len(left.public_path)]:
            raise CompositionError(f"Composed operation path collision: {right.public_name}")


__all__ = ["ComposedApp", "CompositionError", "MountedOperation"]
