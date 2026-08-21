# README Installation Flow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the human-first README lead from the HATEOAS promise through a runnable surface, local MCP configuration, and installation of the authoring skill; publish accurate Python metadata in 0.1.1.

**Architecture:** Keep the root README short and sequential. A separate `hello_mcp.py` starts the already-created MCP adapter over stdio; Codex and Claude Code each start that process from their ordinary local configuration. The advanced Streamable HTTP/ASGI API remains documented in the MCP contract, not the quickstart.

**Tech Stack:** Python packaging metadata, Markdown, pytest repository-metadata tests, GitHub raw-file URLs.

### Task 1: Specify the reader journey with metadata tests

**Files:**
- Modify: `tests/test_repository_metadata.py`

**Step 1: Write the failing test**

Require the root README to contain, in reader order, the HATEOAS/MCP promise, quick code and command, stdio runner plus `~/.codex/config.toml` and `.mcp.json` configuration, and `mkdir -p` / `curl` commands for both shipped skill files. Require Python 3.12--3.14 classifiers in `pyproject.toml`.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repository_metadata.py -v`

Expected: FAIL because the current README has no local config stanzas or skill-download commands, and project metadata has no classifiers.

**Step 3: Commit the failing test**

```bash
git add tests/test_repository_metadata.py
git commit -m "test: specify README installation journey"
```

### Task 2: Implement concise README and metadata updates

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`

**Step 1: Add PyPI classifier metadata**

Add Python 3, 3.12, 3.13, and 3.14 Trove classifiers and change the package version to `0.1.1`.

**Step 2: Make the local MCP flow executable**

Replace the dangling stdio/ASGI sentence with a `hello_mcp.py` snippet and macOS/Linux `~/.codex/config.toml` plus Claude `.mcp.json` stanzas. State that stdio is local-process communication and link advanced remote HTTP hosting to the MCP contract.

**Step 3: Add direct authoring-skill installation**

Show `mkdir -p ~/.codex/skills/agent-friendly-cli-design` and two `curl -fsSL` commands that download `SKILL.md` and `reference.md` from the repository, then link the installed skill and say it applies on the next Codex turn.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_repository_metadata.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add README.md pyproject.toml tests/test_repository_metadata.py
git commit -m "docs: make README install flow actionable"
```

### Task 3: Verify release artifact metadata

**Files:**
- Verify only: `dist/*`

**Step 1: Run all checks and build**

Run: `make check`

Expected: tests, lint, typecheck, and build all pass.

**Step 2: Inspect wheel metadata**

Run: `unzip -p dist/*.whl '*/METADATA' | rg 'Version:|Classifier: Programming Language :: Python'`

Expected: version `0.1.1` and classifiers for 3.12, 3.13, and 3.14.

**Step 3: Commit plan and implementation history as applicable**

```bash
git add docs/plans/2026-08-21-readme-install-flow.md
git commit -m "docs: plan README installation flow"
```

### Task 4: Ship an opinionated package-authoring skill

**Files:**
- Create: `src/agent_surface/skills/agent-surface-authoring/SKILL.md`
- Create: `src/agent_surface/skills/agent-surface-authoring/reference.md`
- Modify: `tests/test_bundled_skill.py`
- Modify: `tests/test_package.py`
- Modify: `README.md`

**Step 1: Write failing packaging and README tests**

Require both sidecars to resolve through `bundled_skill_path`, the package version to match the
release metadata, and the README to install and link the package-specific skill.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_bundled_skill.py tests/test_package.py tests/test_repository_metadata.py -v`

Expected: FAIL because the authoring skill does not exist and the package version is stale.

**Step 3: Add the minimal skill and reference**

Keep `agent-friendly-cli-design` portable. The new skill teaches package-specific `App`, Pydantic,
references, actions, budgets, sibling adapters, and verification.

**Step 4: Verify GREEN**

Run: `uv run pytest tests/test_bundled_skill.py tests/test_package.py tests/test_repository_metadata.py -v`

Expected: PASS.
