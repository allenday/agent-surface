# Generated Click CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate a mountable YAML-first Click CLI from registered operations and teach the complete
HATEOAS workflow through an executable bookstore quickstart.

**Architecture:** Compile immutable CLI plans from Pydantic fields, project those plans into a thin
Click group, and call `OperationRegistry.invoke()` directly. Shared outcome mapping owns stable
errors and bounded actions; Click owns argv capture, lexical parsing, rendering, and exit status.

**Tech Stack:** Python 3.12+, Click 8, Pydantic 2, ruamel.yaml, pytest, Ruff, mypy, uv.

### Task 1: Shared invocation outcomes and reference decoding

**Files:**
- Create: `src/agent_surface/outcomes.py`
- Modify: `src/agent_surface/contracts.py`
- Modify: `src/agent_surface/references.py`
- Modify: `src/agent_surface/__init__.py`
- Create: `tests/test_outcomes.py`
- Modify: `tests/test_references.py`

1. Write failing tests for transport-neutral success/error payloads containing `schema_version`,
   `ok`, `result` or `error`, optional `fix`, and bounded `next_actions`.
2. Test conversion of `OperationError` and `OperationInputError` without traceback or secret values.
3. Test `ReferenceRegistry.decode_type(exact_type, token)` and rejection of unregistered or
   subclass types.
4. Run `.venv/bin/pytest tests/test_outcomes.py tests/test_references.py -v`; observe failures for
   missing APIs.
5. Implement strict frozen contracts, a deny-by-default `ActionProvider` protocol/default, outcome
   builders, and exact-type token decoding.
6. Run focused tests, Ruff, and mypy; expect all green.
7. Commit as `feat: add shared invocation outcomes`.

### Task 2: Compile Pydantic fields into immutable CLI plans

**Files:**
- Create: `src/agent_surface/adapters/__init__.py`
- Create: `src/agent_surface/adapters/click.py`
- Create: `tests/test_click_plans.py`

1. Write failing plan tests for dotted command paths, all-options-by-default, explicit positional
   metadata, required/default values, descriptions, and sensitive fields.
2. Add failing parameterized tests for strings, strict integers, finite floats, booleans, repeated
   lists/sets/tuples, enums, `Literal`, `Path`, optionals, and registered references.
3. Add failing tests for `cli_command_conflict`, leaf/group conflicts, unsupported nested models,
   invalid positional ordering, and duplicate option spelling.
4. Run `.venv/bin/pytest tests/test_click_plans.py -v`; verify RED for the absent compiler.
5. Implement frozen `CliCommandPlan`, `CliFieldPlan`, `CliPlanCompiler`, and stable
   `CliDefinitionError` codes. Use Pydantic field order and exact registered reference types only.
6. Keep numeric bounds and model validators out of Click conversion; they remain Pydantic-owned.
7. Run focused tests, Ruff, and mypy; expect green.
8. Commit as `feat: compile click command plans`.

### Task 3: Generate and mount the Click command tree

**Files:**
- Modify: `src/agent_surface/adapters/click.py`
- Create: `tests/test_click_routing.py`

1. Write failing `CliRunner` tests for nested dotted commands, concise `--help`, deterministic
   ordering, and mounting under an existing consumer group.
2. Test booleans as dual flags, repeated values, enum choices, paths, defaults, and explicit
   positional arguments through real Click parsing.
3. Test raw argv capture including `prog_name` and every original argument boundary.
4. Run the focused module and verify RED.
5. Implement `ClickAdapter` and `build_click_group()`. Override the root entry boundary only as
   needed to snapshot argv before parsing; do not reconstruct it from Click contexts.
6. Generate callbacks from immutable plans and retain shallow parser truth in a context-owned
   invocation record.
7. Run focused tests, Ruff, and mypy; expect green.
8. Commit as `feat: generate click command trees`.

### Task 4: Invoke operations and render stable envelopes

**Files:**
- Modify: `src/agent_surface/adapters/click.py`
- Modify: `src/agent_surface/outcomes.py`
- Create: `tests/test_click_invocation.py`

1. Write failing tests proving sync and async handlers both run through `OperationRegistry.invoke()`
   and match direct results.
2. Write failing tests for YAML auto style, explicit flow/block/JSON rendering, successful parsed
   views, reference decoding, and sensitive-option redaction.
3. Write failing tests for Click syntax errors, Pydantic input errors, domain errors, invalid output,
   oversized responses, and unexpected failures. Assert structured stdout and exits 2, 4, or 70.
4. Write failing destructive-operation tests proving missing `--confirm` exits 3 without calling the
   handler and successful confirmation binds a compatible request field.
5. Run the focused module and verify each failure is caused by missing behavior.
6. Implement payload construction, reference decoding, direct async invocation, outcome mapping,
   safe rendering, redaction, safety gates, and stable exits.
7. Ensure expected failures never leak traceback and internal failures reveal only `internal_error`.
8. Run focused tests, Ruff, and mypy; expect green.
9. Commit as `feat: invoke operations through click`.

### Task 5: Add bounded machine discovery

**Files:**
- Modify: `src/agent_surface/adapters/click.py`
- Create: `tests/test_click_discovery.py`

1. Write failing tests for `operations list`, `operations describe`, `actions list`, and
   `actions explain` using YAML envelopes.
2. Build a 400-operation fixture and test deterministic cursor reachability, default 20-item pages,
   totals, truncation, one immediate continuation, byte budgets, and no ellipsis placeholders.
3. Test parse failures contain a concrete `operations describe` recovery action.
4. Run the focused module and verify RED.
5. Implement reserved discovery commands by reusing `OutputBudget`, `BoundedCollection`, and
   `ActionCatalog`; never create an exhaustive next-action graph.
6. Run focused tests, Ruff, and mypy; expect green.
7. Commit as `feat: add click discovery commands`.

### Task 6: Exercise the reference consumer through Click

**Files:**
- Modify: `tests/reference_consumer/integration.py`
- Modify: `tests/test_reference_consumer.py`
- Create: `tests/test_reference_consumer_click.py`

1. Add a reference codec in the integration boundary without importing Click into the domain.
2. Write failing end-to-end tests for lookup, async pagination, domain errors, and confirmed mutation
   through the generated group.
3. Assert direct and CLI results are semantically equal after removing transport-only command data.
4. Assert the domain fixture contains no `click`, `mcp`, or adapter imports.
5. Run focused tests and verify RED, then add only integration-boundary wiring needed for GREEN.
6. Run all reference-consumer tests, Ruff, and mypy.
7. Commit as `test: run reference consumer through click`.

### Task 7: Deliver the bookstore developer journey

**Files:**
- Rewrite: `README.md`
- Create: `examples/bookstore.py`
- Create: `examples/AGENTS.md`
- Create: `docs/tutorials/bookstore.md`
- Create: `docs/concepts/hateoas.md`
- Create: `docs/how-to/adopt-an-existing-app.md`
- Create: `docs/how-to/references-and-actions.md`
- Create: `docs/reference/cli-contract.md`
- Create: `docs/reference/python-api.md`
- Create: `docs/AGENTS.md`
- Create: `src/agent_surface/AGENTS.md`
- Create: `src/agent_surface/adapters/AGENTS.md`
- Create: `src/agent_surface/skills/AGENTS.md`
- Create: `tests/AGENTS.md`
- Create: `.github/AGENTS.md`
- Modify: `AGENTS.md`
- Modify: `docs/adoption.md`
- Create: `tests/test_bookstore_example.py`
- Modify: `tests/test_repository_metadata.py`

1. Write failing metadata tests requiring a plain-language HATEOAS definition, a complete
   multi-command trajectory, all critical internal links, and scoped agent instructions.
2. Write failing example tests for direct search/inspect/reserve behavior and the generated Click
   trajectory. Assert each invoked next command comes from the preceding envelope.
3. Run the focused tests and verify RED.
4. Implement the consumer-owned bookstore domain, operations, reference codec, explicit action
   provider, and CLI entry point.
5. Rewrite README around a five-minute quickstart and complete unabridged YAML trajectory. Explain
   the behavior before introducing the HATEOAS acronym; distinguish shipped MCP status until #6.
6. Add interlinked tutorial, concept, how-to, and reference pages. Move existing adoption content
   into the new navigation without breaking old links.
7. Add concise inherited `AGENTS.md` files with local invariants and commands, avoiding repetition.
8. Add internal Markdown-link validation and tests preventing claims about unshipped adapters.
9. Run example, metadata, and full test suites; expect green.
10. Commit as `docs: deliver agent-first bookstore quickstart`.

### Task 8: Verify, review, merge, and close issue #5

**Files:** all changed files.

1. Run `make check`; require all tests, Ruff, strict mypy, sdist, and wheel to pass.
2. Search public docs and source for accidental external-consumer names, secrets, TODO placeholders,
   reconstructed argv, and ellipsis omissions.
3. Request independent code review against issue #5 and all three approved design documents.
4. Address every Critical/Important finding with a failing regression test and rerun `make check`.
5. Fast-forward `main`, rerun `make check`, push, and watch Python 3.12–3.14 plus distribution CI.
6. Close issue #5 only after CI succeeds, linking the run.
7. Remove the merged worktree and feature branch.
