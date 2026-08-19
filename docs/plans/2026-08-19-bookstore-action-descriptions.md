# Bookstore Contextual Action Descriptions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure every contextual bookstore action has concise, state-specific descriptive text.

**Architecture:** Keep action copy next to each `Action` constructed by
`BookstoreActions.actions_for()`. Extend the executable bookstore test to traverse each hold-result
branch and assert that no advertised action has an empty description.

**Tech Stack:** Python 3.12, Pydantic, pytest, agent-surface action models

### Task 1: Enforce and populate contextual descriptions

**Files:**
- Modify: `tests/test_bookstore_example.py`
- Modify: `examples/bookstore.py`

**Step 1: Write the failing test**

Extend the contextual-actions test through `holds.get`, `holds.cancel`, and `holds.delete`. For each
result, call `surface.actions.actions_for(...)` and assert every returned action description is
non-empty.

**Step 2: Run the test to verify it fails**

Run: `uv run pytest -q tests/test_bookstore_example.py -k contextual_action_descriptions`

Expected: FAIL because get, cancel, and delete result branches construct actions without
descriptions.

**Step 3: Write the minimal implementation**

Add concise `description=` values to the existing `Action` constructors in those branches. Keep
operation names, commands, bound values, and action counts unchanged.

**Step 4: Run focused and complete verification**

Run: `uv run pytest -q tests/test_bookstore_example.py`

Expected: all bookstore tests pass.

Run: `make check`

Expected: all tests, Ruff, mypy, source distribution, and wheel build pass.

**Step 5: Commit**

```bash
git add examples/bookstore.py tests/test_bookstore_example.py \
  docs/plans/2026-08-19-bookstore-action-descriptions.md
git commit -m "fix: describe contextual hold actions"
```
