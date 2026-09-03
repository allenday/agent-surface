# Typed App composition implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compose independently typed Apps into one Click and MCP surface without crossing child request contracts.

**Architecture:** A transport-neutral mount registry owns public prefixes and collision validation. Click and MCP use that registry to route to child projections; child Apps remain the authority for schema, validation, shared inputs, actions, references, rendering, and manifests.

**Tech Stack:** Python 3.12+, Pydantic, Click, MCP SDK, Hatch manifests, pytest, Ruff, mypy.

**Spec:** `docs/plans/2026-09-03-app-composition-design.md`

## Global Constraints

- Release version is `0.2.0`.
- Never merge child Pydantic request or shared-input models.
- Click and MCP remain sibling projections; neither invokes the other.
- Publish one bounded discovery frontier and never fabricate pagination.
- Preserve canonical envelope redaction, reference codecs, HATEOAS actions, and stable generated usage errors.

---

### Task 1: Define the transport-neutral mount registry

**Files:** Create `src/agent_surface/composition.py`; modify `src/agent_surface/app.py`, `src/agent_surface/__init__.py`; test `tests/test_composition.py`.

**Interfaces:** Produce `ComposedApp`, `MountedApp`, and `CompositionError`. `ComposedApp.mount(prefix: str | tuple[str, ...], app: App, **projection_options) -> ComposedApp` returns the builder and `operations()` returns deterministic public-to-child routes.

- [ ] Write tests for two mounts (`diagram.render`, `diagram.project`), nested prefixes, duplicate paths, and prefix collisions.
- [ ] Run `pytest tests/test_composition.py -v` and confirm missing composition API failures.
- [ ] Implement immutable mount records, prefix normalization, deterministic collision validation, and public exports.
- [ ] Re-run `pytest tests/test_composition.py -v`; run Ruff and mypy for new source.
- [ ] Commit `feat: add typed app composition registry`.

### Task 2: Project composition through Click

**Files:** Modify `src/agent_surface/adapters/click.py`; test `tests/test_click_composition.py`.

**Interfaces:** Consume `ComposedApp.operations()` routes. Produce one Click group tree whose prefixed leaf delegates to the selected child’s compiled plan and projection options.

- [ ] Write tests proving `diagram render` consumes only render shared input while `diagram project` accepts only `--source`; test parse errors, canonical envelope, actions, and collision errors.
- [ ] Run the focused tests and observe RED.
- [ ] Implement public-path tree assembly and child-local payload/renderer/reference/action dispatch without mounting an adapter through another adapter.
- [ ] Run focused tests, `tests/test_click_*.py`, Ruff, and mypy.
- [ ] Commit `feat: project composed apps through Click`.

### Task 3: Project composition through MCP and manifests

**Files:** Modify `src/agent_surface/adapters/mcp.py`, `src/agent_surface/manifest.py`; test `tests/test_mcp_composition.py`, `tests/test_manifest.py`.

**Interfaces:** Consume the same composition routes. Produce one MCP tool catalog with prefixed names and manifest records containing child provenance plus public paths.

- [ ] Write tests for prefixed MCP schemas/calls, child-local shared fields, canonical envelopes/actions, deterministic pages, and manifest verification/collision failures.
- [ ] Run focused tests and observe RED.
- [ ] Implement direct child adapter dispatch and composed manifest generation/verification; retain compatibility for `MCPAdapter.compose` where documented.
- [ ] Run focused MCP/manifest tests, Ruff, and mypy.
- [ ] Commit `feat: project composed apps through MCP and manifests`.

### Task 4: Publish developer documentation and release `0.2.0`

**Files:** Modify `docs/reference/python-api.md`, `docs/reference/mcp-contract.md`, `docs/README.md`, `README.md`, `pyproject.toml`, `uv.lock`, `src/agent_surface/__init__.py`, `tests/test_package.py`; create `docs/concepts/app-composition.md` and an executable example under `examples/`.

**Interfaces:** Document only the verified public `ComposedApp.mount` API and its Click/MCP example. Produce version `0.2.0` metadata.

- [ ] Write the runnable example and docs tests/metadata assertions first; run them to observe missing API/documentation failures.
- [ ] Write the concept/reference material with child-input isolation, collision behavior, and Click/MCP commands; add navigation links.
- [ ] Bump all release version authorities to `0.2.0` and update the lockfile.
- [ ] Run docs link/example checks, `make check`, `uv build`, and inspect built wheel contents.
- [ ] Commit `docs: document typed app composition` and `chore: release 0.2.0`.

### Task 5: Integrate, critique, and release

**Files:** No production files unless critique finds a defect.

- [ ] Obtain an independent complete-revision critique covering composition boundaries, adapter sibling separation, manifests, and documentation accuracy.
- [ ] Run GitHub Actions CI for the final PR revision; record immutable run URLs and commit SHA in the linked issues.
- [ ] Validate the example against installed built artifacts and verify the GitHub Release tag equals `v0.2.0`.
- [ ] Merge the approved PR, create GitHub Release `v0.2.0`, approve the `pypi` environment, and verify the OIDC publishing workflow succeeds.
