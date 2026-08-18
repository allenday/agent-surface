"""Access skills bundled with the distribution."""

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path


@contextmanager
def bundled_skill_path(name: str) -> Iterator[Path]:
    """Yield a filesystem path for a bundled skill directory."""

    resource = files(__package__).joinpath(name)
    if not resource.is_dir():
        raise KeyError(f"Unknown bundled skill: {name}")
    with as_file(resource) as path:
        yield path


__all__ = ["bundled_skill_path"]
