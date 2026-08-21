# README MCP Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship 0.1.2 with an accurate HATEOAS link and a single-file stdio MCP quickstart.

**Architecture:** `hello.py` stays the only quickstart artifact. Its direct `--mcp` mode runs the
MCP adapter over stdio before delegating all ordinary argv to Click. The documentation is protected
by repository metadata assertions.

**Tech Stack:** Python, Click, MCP adapter, Markdown, pytest, Hatch packaging.

### Task 1: Specify corrected quickstart behavior

**Files:**
- Modify: `tests/test_repository_metadata.py`
- Modify: `tests/test_package.py`

**Step 1: Write failing tests**

Require the Wikipedia HATEOAS URL, `hello.py` plus `--mcp`, absence of `hello_mcp.py`, and package
version `0.1.2`.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_repository_metadata.py tests/test_package.py -v`

Expected: FAIL because 0.1.1 has the old link, extra runner, and old version.

### Task 2: Implement the concise one-file quickstart

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `src/agent_surface/__init__.py`
- Modify: `uv.lock`

**Step 1: Change the citation and runner snippet**

Use Wikipedia, add `asyncio`/`sys` to `hello.py`, dispatch exact `--mcp`, and update both client
configuration stanzas.

**Step 2: Bump release metadata**

Change project, package, and lockfile versions to `0.1.2`.

**Step 3: Verify GREEN**

Run: `uv run pytest tests/test_repository_metadata.py tests/test_package.py -v`

Expected: PASS.

### Task 3: Verify and release

**Step 1: Run full verification**

Run: `make sync && make check`

Expected: tests, lint, type check, and build pass.

**Step 2: Review and publish**

Review the committed diff, merge to main, then use the Trusted Publishing workflow: TestPyPI clean
install first, followed by a protected PyPI release.
