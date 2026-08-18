# Agent Surface Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python package that projects typed operations as a YAML-first agent CLI, MCP server, and schemas.

**Architecture:** A transport-neutral registry and invocation engine own Pydantic contracts, action synthesis, references, envelopes, and budgets. Click, MCP, and schema modules adapt the registry without depending on one another.

**Tech Stack:** Python 3.12+, Pydantic 2, Click 8, ruamel.yaml, official MCP Python SDK 1.x, pytest, Ruff, mypy, uv/hatchling, and an isolated `.venv`.

### Task 1: Package scaffold

**Files:** Create `pyproject.toml`, `README.md`, `src/agent_surface/__init__.py`, and `tests/test_package.py`.

1. Write a failing import/version test.
2. Run `uv run pytest tests/test_package.py -v` and confirm the import fails.
3. Add the minimal package, build metadata, dependency groups, and version.
4. Run the test and `uv build`; confirm both pass.

### Task 2: Shared contract models

**Files:** Create `src/agent_surface/contracts.py` and `tests/test_contracts.py`.

1. Test success and error envelopes, argv preservation, action collection metadata, and stable YAML-ready dumps.
2. Confirm failures because the models do not exist.
3. Implement `CommandView`, `Action`, `ActionCollection`, `ErrorDetail`, `ErrorInfo`, `SuccessEnvelope`, and `ErrorEnvelope` as strict Pydantic models.
4. Run the focused tests and commit the green state.

### Task 3: Operation registry and invocation

**Files:** Create `src/agent_surface/operations.py`, `src/agent_surface/app.py`, and `tests/test_operations.py`.

1. Test decorator registration, duplicate rejection, Pydantic input validation, sync/async handlers, typed output validation, and domain-error translation.
2. Confirm the focused suite fails for missing behavior.
3. Implement immutable operation definitions, `App.operation`, lookup/list/describe, and one async invocation path.
4. Run the focused and full suites.

### Task 4: Reference codecs

**Files:** Create `src/agent_surface/references.py` and `tests/test_references.py`.

1. Test stable encode/decode/display separation, duplicate codec rejection, unknown kinds, and round trips.
2. Confirm failures.
3. Implement `ObjectRef`, `ReferenceCodec` protocol, and `ReferenceRegistry`.
4. Run focused tests and property-style parameterized round trips.

### Task 5: Opt-in reflective action plans

**Files:** Create `src/agent_surface/actions.py` and `tests/test_actions.py`.

1. Test that only `@action` methods register; class-level model fields and signatures compile; properties are not evaluated; explicit bindings win; ambiguity fails; defaults and unbound slots work.
2. Confirm failures.
3. Implement `action`, binding metadata for `Annotated`, compiled `ActionPlan`, and deterministic binding using `inspect.signature` and Pydantic validation.
4. Run focused tests.

### Task 6: Bounded action synthesis

**Files:** Extend `actions.py`; create `src/agent_surface/policy.py` and `tests/test_action_policy.py`.

1. Test item/byte budgets, stable ranking, immediate pagination only, high-branch-factor collection sources, explicit truncation, and discovery actions.
2. Confirm failures.
3. Implement `OutputPolicy` and bounded action synthesis without collection Cartesian expansion.
4. Run focused and full suites.

### Task 7: YAML-first rendering

**Files:** Create `src/agent_surface/rendering.py` and `tests/test_rendering.py`.

1. Test block, flow, and auto styles; scalar leaf flow bias; whole-small-document flow; stable width rules; no semantic ellipsis; JSON projection; serialized-byte enforcement.
2. Confirm failures.
3. Implement `YamlRenderPolicy`, deterministic node styling with ruamel.yaml, JSON rendering, and structured size failures.
4. Run focused tests and snapshot representative envelopes.

### Task 8: Click adapter

**Files:** Create `src/agent_surface/adapters/click.py`, `src/agent_surface/adapters/__init__.py`, and `tests/test_click_adapter.py`.

1. Test generated commands, positional/option/flag binding, YAML default, format/style overrides, stdout/stderr separation, exit codes, operations discovery, and repairable parse errors.
2. Confirm failures using Click's isolated runner.
3. Implement a generated Click group that invokes the shared engine.
4. Run focused and full suites.

### Task 9: MCP adapter

**Files:** Create `src/agent_surface/adapters/mcp.py` and `tests/test_mcp_adapter.py`.

1. Test tool registration, input/output schemas, successful structured content, tool errors, and safety annotations without starting a network server.
2. Confirm failures.
3. Implement the official FastMCP adapter behind the `mcp` optional extra.
4. Run focused and full suites.

### Task 10: Schema exports

**Files:** Create `src/agent_surface/schema.py` and `tests/test_schema.py`.

1. Test per-operation JSON Schema and deterministic OpenAPI 3.1 export using stable operation IDs and Pydantic schemas.
2. Confirm failures.
3. Implement registry schema projections; do not add an HTTP runtime.
4. Run focused tests and validate the exported document structurally.

### Task 11: Example application and documentation

**Files:** Create `examples/repo_app.py`, `tests/test_example.py`, and expand `README.md`.

1. Write an end-to-end test invoking one operation directly, through Click, and through the MCP adapter.
2. Confirm it fails before the example exists.
3. Add the example, installation instructions, command tree, envelopes, reflection/reference guidance, budgets, and extension points.
4. Run the example test, full test suite, Ruff, mypy, and `uv build`.

### Task 12: Release readiness

1. Run `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src`, and `uv build`.
2. Inspect wheel contents and install the wheel into a temporary uv environment.
3. Smoke-test the installed CLI and import package.
4. Record any deferred work; do not publish without explicit authorization.
