# AGENTS.md

These instructions apply to the entire repository. User instructions take precedence.

## Project

`agent-surface` is a Python 3.12+ library that projects typed operations through CLI, MCP, and
schema adapters. Pydantic models and the operation registry are the source of truth. Agent-facing
responses are YAML-first, bounded, discoverable, and transport-neutral.

## Setup and checks

Work from the repository root and use the project venv. Do not install dependencies globally.

```bash
uv sync --frozen --all-extras --dev
make check
```

Useful focused commands:

```bash
uv run pytest tests/test_operations.py -v
uv run ruff check .
uv run mypy src
uv build
```

`make check` is the completion gate: tests, Ruff, mypy, and distribution builds must all pass.

## Repository map

- `src/agent_surface/contracts.py`: stable transport-neutral envelopes and actions
- `src/agent_surface/operations.py`: typed registration and invocation
- `src/agent_surface/app.py`: public application/decorator API
- `src/agent_surface/skills/`: bundled `SKILL.md`, `reference.md`, and future sidecars
- `tests/`: executable behavior and package-resource contracts
- `docs/plans/`: approved designs and implementation plans

## Implementation rules

- Use test-driven development for behavior changes: observe RED, implement minimally, then GREEN.
- Keep public models strict and serializable. Preserve stable error codes and original argv
  boundaries.
- Keep YAML as the default structured representation. Flow style is preferred for small leaf
  collections; never use ellipsis as an omission marker.
- Treat `next_actions` as a bounded relevant frontier. Expose totals, truncation, and a concrete
  discovery action instead of expanding high-branch-factor graphs.
- Introspection is opt-in: decorated methods and Pydantic fields may produce candidates, but
  explicit policy decides which actions are published.
- Never use `str(object)` as a stable reference. Use an explicit reference codec.
- Keep Click and MCP adapters thin; business logic belongs in the shared operation layer.
- Preserve bundled skill sidecars as package data. When they change, test both source access and
  built-wheel contents.
- Do not commit `.venv/`, `dist/`, caches, credentials, or generated artifacts.

## Changes and releases

Keep commits focused and include tests for behavior changes. Do not push, publish, or modify a
release workflow unless the user explicitly requests it. Publishing uses GitHub OIDC Trusted
Publishing; never add PyPI passwords or API tokens to repository files or workflow secrets.

Before handing off, inspect the diff and working tree, run `make check`, and report any checks that
could not run.
