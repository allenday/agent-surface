# Agent-Friendly Repository Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give agents and public contributors a concise, executable repository guide with verified CI and credential-free TestPyPI/PyPI publishing.

**Architecture:** Human orientation stays in `README.md`; executable agent instructions live in root `AGENTS.md`; contributor and release procedures remain in focused sidecars. GitHub Actions reuse the locked development environment, build distributions once, and publish with narrowly scoped OIDC permissions.

**Tech Stack:** Python 3.12+, uv, Hatchling, pytest, Ruff, mypy, GitHub Actions, PyPI Trusted Publishing

### Task 1: Add executable repository checks

**Files:**
- Create: `Makefile`
- Create: `tests/test_repository_metadata.py`
- Modify: `pyproject.toml`

1. Add failing metadata tests for the Python baseline, required project URLs, license file, agent instructions, workflows, and package data.
2. Run `.venv/bin/pytest tests/test_repository_metadata.py -v` and confirm the missing repository surface fails.
3. Add canonical `make` targets and align Ruff with Python 3.12.
4. Run the focused tests and then `make check`.
5. Commit the executable repository contract.

### Task 2: Write concise public documentation

**Files:**
- Modify: `README.md`
- Create: `AGENTS.md`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Create: `LICENSE`
- Create: `docs/releasing.md`

1. Expand the README with badges, status, installation, a minimal typed operation, architecture links, and contributor links.
2. Add exact setup, architecture, testing, YAML, Pydantic, package-data, and completion instructions to `AGENTS.md`.
3. Add focused contributor, security, and trusted-publishing instructions.
4. Run metadata tests and Markdown/link sanity checks.
5. Commit the documentation surface.

### Task 3: Add GitHub contributor templates

**Files:**
- Create: `.github/ISSUE_TEMPLATE/bug.yml`
- Create: `.github/ISSUE_TEMPLATE/feature.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/pull_request_template.md`
- Create: `.github/dependabot.yml`

1. Add concise structured issue forms and a focused PR checklist.
2. Configure weekly dependency updates for uv and GitHub Actions.
3. Parse all repository YAML and assert required metadata in the repository tests.
4. Commit the contributor templates.

### Task 4: Add CI and trusted publishing

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Modify: `tests/test_repository_metadata.py`

1. Add failing assertions for event triggers, the Python 3.12–3.14 matrix, least-privilege permissions, environments, and publishing conditions.
2. Add CI jobs for tests, static checks, distribution builds, and installed-wheel verification.
3. Add one-build release automation: manual dispatch publishes to TestPyPI; published GitHub Releases publish to PyPI.
4. Pin every action to an immutable commit and retain version comments for Dependabot/readability.
5. Run focused tests, `make check`, workflow syntax checks, and a clean distribution build.
6. Commit automation.

### Task 5: Connect and verify the repository

**Files:**
- Modify only if verification exposes a defect.

1. Configure `origin` as `git@github.com:allenday/agent-surface.git` and verify it without pushing.
2. Run the complete test, Ruff, mypy, build, wheel-content, and repository-metadata checks from a clean state.
3. Inspect the final diff and working tree, then report the two external trusted-publisher registrations still required from the owner.
