# Human-First Root README Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the root README into a concise human-first entry point while preserving direct paths to
the deeper agent-facing contracts and shipped skill.

**Architecture:** Replace the long root-level bookstore transcript and detailed reference sections
with an HATEOAS-led promise, a copy/paste 30-second Pydantic example, one compact trajectory, and
three reader paths. Leave detailed operational material in the existing tutorial, how-to, and
reference documents.

**Tech Stack:** Markdown, pytest repository-metadata checks

### Task 1: Protect the human-first README contract

**Files:**
- Modify: `tests/test_repository_metadata.py`

**Step 1: Write the failing test**

Replace the root-README trajectory assertion with requirements for the HATEOAS and MCP external
links, the `pip install` and Pydantic adopter path, `next_actions`, bookstore/tutorial destination,
and direct packaged `SKILL.md` path. Add a length ceiling that leaves the deeper transcript outside
the root page.

**Step 2: Run the test to verify it fails**

Run: `uv run pytest -q tests/test_repository_metadata.py -k human_first`

Expected: FAIL because the current README lacks the direct skill and external concept links and is
too long for the new entry-point contract.

### Task 2: Rewrite the root README

**Files:**
- Modify: `README.md`

**Step 1: Implement the approved information flow**

Write the linked HATEOAS/MCP promise, a 30-second library-adopter snippet, one compact YAML
`next_actions` example, reader-path links, a prominent packaged-skill link, and a brief principles
block. Preserve badges, install commands, contributing, and license links.

**Step 2: Run focused documentation checks**

Run: `uv run pytest -q tests/test_repository_metadata.py -k 'human_first or public_markdown'`

Expected: PASS.

### Task 3: Verify and commit

**Files:**
- Modify: `README.md`
- Modify: `tests/test_repository_metadata.py`

**Step 1: Run the complete repository gate**

Run: `make check`

Expected: all tests, Ruff, mypy, source distribution, and wheel build pass.

**Step 2: Commit**

```bash
git add README.md tests/test_repository_metadata.py \
  docs/plans/2026-08-21-human-first-readme.md
git commit -m "docs: make root readme human-first"
```
