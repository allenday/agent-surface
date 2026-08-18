.PHONY: sync test lint typecheck build check

sync:
	uv sync --frozen --all-extras --dev

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run mypy src

build:
	uv build

check: test lint typecheck build
