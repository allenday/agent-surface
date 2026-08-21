# Progressive Disclosure DX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the repository's human and agent entry points skimmable, truthful, and action-oriented.

**Architecture:** Reorder the root README around a visible HATEOAS trajectory before the optional adoption paths. Give directories with genuinely distinct work concise local instructions, and keep durable docs—not plans—the canonical navigation spine.

**Tech Stack:** Markdown, pytest repository-metadata checks, GitHub issues.

### Task 1: Rebuild the root README's first-screen path

**Files:**
- Modify: `README.md`
- Modify: `tests/test_repository_metadata.py`

1. Add a failing metadata assertion for promise → visible trajectory → library use → MCP → authoring guidance.
2. Run the focused test and observe failure.
3. Reorder and tighten the README around that path; make each install claim truthful.
4. Re-run the focused test.
5. Commit the change and close issues #7 and #8 after full verification.

### Task 2: Complete local guidance where it differs

**Files:**
- Modify: `AGENTS.md`
- Create or modify: scoped `AGENTS.md` files only where local work has distinct rules
- Modify: `tests/test_repository_metadata.py`

1. Add a failing assertion for the intended scoped instruction hierarchy.
2. Add concise sidecars with immediate commands, constraints, and local maps.
3. Re-run the focused test and commit.

### Task 3: Strengthen durable documentation navigation

**Files:**
- Modify: `README.md`, `docs/AGENTS.md`, and relevant durable docs
- Modify: `tests/test_repository_metadata.py`

1. Add a failing assertion for a durable documentation map and reliable badges.
2. Keep plans as history, never a primary entry path.
3. Re-run focused and complete repository verification.
4. Commit, push, and close issue #10.
