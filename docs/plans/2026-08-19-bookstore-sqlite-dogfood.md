# SQLite Bookstore Dogfood Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist bookstore holds in SQLite, expose complete CRUD through Click and MCP, and document
real Codex and Claude Code registration.

**Architecture:** Keep seeded books in the example domain while one SQLite connection owns durable
hold state. Add typed get/delete operations and contextual actions, then start the existing MCP
adapter from a dedicated stdio module and executable wrapper.

**Tech Stack:** Python 3.12, sqlite3, Pydantic 2, Click, MCP Python SDK 2, pytest, uv.

### Task 1: Persist complete hold CRUD

**Files:**
- Modify: `examples/bookstore.py`
- Modify: `tests/test_bookstore_example.py`

1. Write failing temporary-database tests for create, duplicate rejection, read across a new surface,
   cancel persistence, delete, and missing reads.
2. Run the focused tests and verify RED for the absent persistence/get/delete behavior.
3. Add the minimal SQLite schema, request models, handlers, registrations, and stable errors.
4. Publish bounded concrete get/cancel/delete actions with MCP `bound` values.
5. Run focused tests, Ruff, and mypy; expect green.
6. Commit as `feat: persist bookstore hold crud`.

### Task 2: Add a real bookstore MCP process

**Files:**
- Create: `examples/bookstore_mcp.py`
- Create: `examples/bookstore-mcp`
- Modify: `tests/test_bookstore_example.py`

1. Write a failing stdio subprocess test that launches the example wrapper with a temporary database
   and performs create/get/cancel/delete over protocol streams.
2. Verify RED because the MCP executable is absent.
3. Add the minimal async runner and repository-relative executable wrapper.
4. Verify deterministic teardown, persisted state, executable permissions, Ruff, and mypy.
5. Commit as `feat: add bookstore mcp runner`.

### Task 3: Document and dogfood client integration

**Files:**
- Modify: `README.md`
- Modify: `docs/tutorials/bookstore.md`
- Modify: `docs/reference/mcp-contract.md`
- Modify: `tests/test_repository_metadata.py`
- Modify outside repository after merge: `~/.codex/config.toml`

1. Write failing metadata tests requiring persistent CRUD and Codex/Claude configuration guidance.
2. Add exact source-checkout commands and config shapes, linking official Codex and Claude Code MCP
   documentation.
3. Run documentation, link, example, and full project checks.
4. Commit as `docs: add mcp client integration guide`.
5. Request independent review and address every Critical/Important finding with regression tests.
6. Fast-forward main, rerun `make check`, push, and wait for CI.
7. Register the stable main-checkout wrapper with `codex mcp add`, verify with `codex mcp get`, and ask
   the user to reconnect the session so the client can attach it.
