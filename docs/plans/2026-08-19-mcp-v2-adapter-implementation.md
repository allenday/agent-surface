# Native MCP v2 Adapter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Project registered operations as native, paginated MCP v2 tools with structured outcomes and
semantic equivalence to direct and Click invocation.

**Architecture:** Compile MCP tool definitions directly from operation Pydantic schemas and serve
them through the official low-level MCP v2 API. Calls dispatch to `OperationRegistry.invoke()` and
reuse shared outcomes, references, actions, budgets, and safety gates without importing Click.

**Tech Stack:** Python 3.12+, MCP Python SDK 2.x, Pydantic 2, anyio, pytest, uv.

### Task 1: Establish the optional MCP v2 boundary

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/agent_surface/adapters/mcp.py`
- Modify: `src/agent_surface/adapters/__init__.py`
- Create: `tests/test_mcp_imports.py`

1. Write failing subprocess tests proving core and Click imports work when MCP is unavailable, the
   MCP adapter gives an actionable extra-install message, and the MCP adapter never imports Click.
2. Assert the optional dependency is `mcp>=2,<3` and the locked version is on the 2.x stable line.
3. Run `.venv/bin/pytest tests/test_mcp_imports.py -v`; verify RED for the absent adapter.
4. Implement lazy optional imports and the public adapter module without registering tools yet.
5. Run focused tests, Ruff, and mypy; expect green.
6. Commit as `feat: establish mcp v2 adapter boundary`.

### Task 2: Compile native tools and paginated discovery

**Files:**
- Modify: `src/agent_surface/adapters/mcp.py`
- Create: `tests/test_mcp_tools.py`

1. Write failing in-memory client tests for exact dotted names, summaries, validation input schemas,
   success output schemas, and all four safety annotations.
2. Add a 400-operation fixture and failing tests for deterministic opaque cursor pages, complete
   reachability, bounded page size, malformed cursors, and side-effect-free discovery.
3. Run the focused module and verify RED.
4. Implement immutable MCP tool plans and low-level list handling from
   `model_json_schema(mode="validation")` and shared success payload schemas.
5. Map operation metadata to MCP v2 annotations and keep exact stable operation names.
6. Reuse a versioned cursor codec; do not mutate tool visibility in response to calls.
7. Run focused tests, Ruff, and mypy; expect green.
8. Commit as `feat: compile native mcp tools`.

### Task 3: Invoke tools with structured outcomes and safety

**Files:**
- Modify: `src/agent_surface/adapters/mcp.py`
- Create: `tests/test_mcp_invocation.py`

1. Write failing `Client(server, raise_exceptions=True)` tests for sync and async operations,
   Pydantic constraints, explicit references, and structured success content.
2. Test compatibility text content is bounded YAML describing the same public outcome.
3. Write failing tests for invalid input, domain errors, invalid output, unexpected failures, and
   secret redaction. Assert stable structured errors and `is_error=true`.
4. Write failing destructive-operation tests requiring explicit `confirm: true` before the handler
   runs and binding a compatible request field.
5. Run focused tests and verify RED.
6. Implement direct registry dispatch, reference decoding, shared outcome mapping, structured/text
   content, safety gates, and output-schema validation.
7. Run focused tests, Ruff, and mypy; expect green.
8. Commit as `feat: invoke operations through mcp`.

### Task 4: Add runtime entry points and stdio smoke coverage

**Files:**
- Modify: `src/agent_surface/adapters/mcp.py`
- Create: `tests/fixtures/mcp_stdio_server.py`
- Create: `tests/test_mcp_runtime.py`

1. Write failing tests for obtaining the native server object and starting supported stdio and
   streamable-HTTP runners without coupling them to application business logic.
2. Write one stdio subprocess smoke test that lists and calls a tool over real protocol streams.
3. Run the focused module and verify RED.
4. Implement minimal runner methods by delegating transport lifecycle to MCP v2.
5. Run focused tests and ensure subprocess teardown is deterministic.
6. Commit as `feat: add mcp runtime entry points`.

### Task 5: Prove direct, Click, and MCP equivalence

**Files:**
- Modify: `tests/reference_consumer/integration.py`
- Create: `tests/test_reference_consumer_mcp.py`
- Modify: `tests/test_reference_consumer_click.py`

1. Write failing tests invoking lookup, async list, expected failure, and confirmed mutation through
   all three paths.
2. Normalize transport envelopes and assert identical domain result or stable error semantics.
3. Assert the consumer domain imports neither adapter and the MCP adapter imports no Click module.
4. Add integration-boundary MCP construction only; do not alter consumer-owned domain models.
5. Run all reference-consumer tests, Ruff, and mypy; expect green.
6. Commit as `test: prove adapter semantic equivalence`.

### Task 6: Extend the bookstore journey through MCP

**Files:**
- Modify: `README.md`
- Modify: `examples/bookstore.py`
- Modify: `docs/tutorials/bookstore.md`
- Create: `docs/reference/mcp-contract.md`
- Modify: `docs/reference/python-api.md`
- Modify: `docs/AGENTS.md`
- Modify: `tests/test_bookstore_example.py`
- Modify: `tests/test_repository_metadata.py`

1. Write failing tests for constructing the bookstore MCP server and following the same
   search/inspect/reserve trajectory through the in-memory client.
2. Replace all README “planned MCP” markers with tested shipped behavior and add a concise MCP
   quickstart linked to the complete tutorial and reference.
3. Document native tool names, schemas, annotations, structured success/errors, discovery cursors,
   runtime commands, and the Click/MCP sibling boundary.
4. Validate every internal link and execute every documented bookstore path in tests.
5. Run focused documentation/example tests, then `make check`; expect green.
6. Commit as `docs: extend bookstore quickstart through mcp`.

### Task 7: Verify, review, merge, and close issue #6

**Files:** all changed files.

1. Run `uv sync --frozen --all-extras --dev` and `make check` in the Python 3.12+ worktree.
2. Build the wheel, install it with and without `[mcp]` in fresh temporary venvs, and smoke imports.
3. Request independent review against the approved MCP and DX designs.
4. Address every Critical/Important finding with a failing regression test and rerun all checks.
5. Fast-forward `main`, rerun `make check`, push, and watch Python 3.12–3.14 plus distribution CI.
6. Close issue #6 only after CI succeeds, linking the run.
7. Remove the merged worktree and feature branch.
