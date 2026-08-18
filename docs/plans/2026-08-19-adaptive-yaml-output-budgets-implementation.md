# Adaptive YAML and Output Budgets Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add deterministic YAML/JSON rendering, explicit bounded collections, and stable item and
byte budgets without silent truncation or ellipsis placeholders.

**Architecture:** New immutable budget contracts own limits and explicit collection truncation. A
separate rendering module converts Pydantic or JSON-compatible values, applies adaptive YAML style,
and enforces limits; its envelope entry point translates limit failures into the existing structured
error contract.

**Tech Stack:** Python 3.12, Pydantic v2, ruamel.yaml 0.19, pytest, Ruff, mypy

### Task 1: Add budget contracts and explicit bounded collections

**Files:**
- Create: `src/agent_surface/budgets.py`
- Create: `tests/test_budgets.py`
- Modify: `src/agent_surface/__init__.py`

1. Write failing tests requiring immutable `OutputBudget` defaults of 20 items and 65,536 UTF-8
   bytes, positive-value validation, and a structured `OutputBudgetExceeded` exception.
2. Add failing tests for `BoundedCollection[T]`: exact counts, a continuation `Action` required
   exactly when truncated, `from_sequence` returning a complete collection below the limit, and
   explicit slicing only when a continuation is supplied.
3. Assert that exceeding the item limit without a continuation raises code
   `item_budget_exceeded`, includes the original count and limit, and never adds an ellipsis item.
4. Run `.venv/bin/pytest tests/test_budgets.py -v` and confirm failure because the module is absent.
5. Implement the minimal frozen Pydantic contracts, validators, generic constructor, and exception.
6. Export the public contracts from `agent_surface.__init__`.
7. Run the focused tests, Ruff, and mypy; commit as `feat: add explicit output budgets`.

### Task 2: Add deterministic adaptive YAML and JSON rendering

**Files:**
- Create: `src/agent_surface/rendering.py`
- Create: `tests/test_rendering.py`
- Create: `tests/golden/render-auto.yaml`
- Create: `tests/golden/render-flow.yaml`
- Create: `tests/golden/render-block.yaml`
- Modify: `src/agent_surface/__init__.py`

1. Write failing tests for `RenderOptions`, default YAML/auto selection, and explicit `yaml`/`json`
   plus `auto`/`flow`/`block` literals.
2. Create a nested Pydantic fixture with Unicode, small leaf mappings and sequences, and a multiline
   string. Add golden assertions for all three YAML styles.
3. Require auto mode to flow-style leaf collections only when they contain at most six values, no
   multiline scalar, and fit within 100 columns. Require multiline text to use a literal block.
4. Require flow mode to use flow collections throughout and block mode to use block collections
   throughout. Assert safe YAML round trips preserve the fixture value.
5. Require JSON to preserve Unicode, field order, and values through `json.loads`.
6. Run `.venv/bin/pytest tests/test_rendering.py -v` and confirm failure because rendering is absent.
7. Implement JSON-compatible normalization, deterministic JSON output, ruamel `CommentedMap` and
   `CommentedSeq` style annotation, literal multiline scalars, and YAML dumping without key sorting.
8. Update the three golden files from deliberately failing expected content using the observed,
   reviewed renderer output; do not generate them from inside the test.
9. Run focused tests, Ruff, and mypy; commit as `feat: add adaptive YAML rendering`.

### Task 3: Enforce item and byte budgets without partial output

**Files:**
- Modify: `src/agent_surface/rendering.py`
- Modify: `tests/test_rendering.py`

1. Add failing tests showing low-level `render` rejects an unmarked sequence over `max_items` with
   code `item_budget_exceeded` and a precise data path, while a valid `BoundedCollection` renders.
2. Add a failing semantic test proving no rendered or parsed collection contains an ellipsis
   placeholder.
3. Add failing UTF-8 boundary tests: a document fits when `max_bytes` equals its encoded length and
   fails with `response_too_large` one byte below it. Assert measured and allowed byte counts.
4. Implement recursive sequence validation before serialization and exact UTF-8 byte measurement
   after serialization. Never slice, replace, or partially emit a raw value.
5. Run focused tests, Ruff, and mypy; commit as `feat: enforce rendering output budgets`.

### Task 4: Render structured envelope errors and publish usage

**Files:**
- Modify: `src/agent_surface/rendering.py`
- Modify: `src/agent_surface/__init__.py`
- Modify: `tests/test_rendering.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `tests/test_repository_metadata.py`

1. Add a failing test that passes an oversized `SuccessEnvelope` to `render_envelope` and requires a
   complete parseable `ErrorEnvelope` retaining the original `command`, code
   `response_too_large`, structured measurements, recovery guidance, and no partial result.
2. Add a failing test showing an impossibly small budget re-raises `OutputBudgetExceeded` instead of
   emitting an over-budget or malformed error document.
3. Implement envelope translation with empty bounded `next_actions`; reuse `render` for the compact
   error so the same byte contract applies.
4. Add concise README examples for YAML auto/flow/block, JSON, explicit `BoundedCollection`, and
   `render_envelope`. Add repository instructions that renderers must never fabricate pagination or
   silently truncate.
5. Extend repository metadata tests to require the rendering API and principles in public docs.
6. Run focused tests and `make check`.
7. Verify the golden files contain no `...` scalar, retain the semantic no-placeholder test, and
   confirm new public files contain no external consumer name, organization, URL, or identifier.
8. Commit as `docs: publish bounded rendering contract`.
9. Request independent code review, address findings one at a time, and rerun `make check`.
10. Fast-forward `main`, rerun `make check`, push, watch GitHub Actions, and close issue #3 only after
    all Python 3.12–3.14 and distribution jobs pass.
