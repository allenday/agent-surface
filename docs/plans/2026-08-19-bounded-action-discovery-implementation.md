# Bounded Action Discovery and Reference Codecs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add stable reference codecs, narrow action-candidate introspection, explicit policy-gated
publication, and cursor-bounded action discovery.

**Architecture:** Reference identity is handled by an exact-type codec registry. An action compiler
creates immutable plans from registered Pydantic models and explicitly decorated signatures; a
separate publisher binds only safe values under an explicit policy, and an in-memory catalog pages
the resulting transport-neutral `Action` models.

**Tech Stack:** Python 3.12, Pydantic v2, inspect, base64, pytest, Ruff, mypy

### Task 1: Add explicit reference codecs

**Files:**
- Create: `src/agent_surface/references.py`
- Create: `tests/test_references.py`
- Modify: `src/agent_surface/__init__.py`

1. Write failing tests for frozen `ReferenceValue(kind, id, label)` and a generic
   `ReferenceCodec[T]` protocol implemented by a domain codec.
2. Require `ReferenceRegistry.register`, exact-type lookup, structured `encode`, and kind-directed
   `decode`; verify encoded IDs round-trip and display labels remain independent.
3. Add failing tests for duplicate kind/type registration, wrong decoded types, unstable
   encode/decode round trips, and a custom object with a tempting `__str__` but no codec.
4. Require canonical scalar tokens for strings, booleans, integers, finite floats, `None`, and
   string-valued enums; reject non-finite floats and unsupported objects.
5. Run `.venv/bin/pytest tests/test_references.py -v` and observe failure because the module is absent.
6. Implement the minimal protocol, immutable contracts, registry, scalar encoder, and stable
   `ReferenceError` subclasses with codes and fixes.
7. Export the public reference API, run focused tests, Ruff, and mypy, then commit as
   `feat: add explicit reference codecs`.

### Task 2: Compile narrow action candidates

**Files:**
- Create: `src/agent_surface/actions.py`
- Create: `tests/test_action_compiler.py`
- Modify: `src/agent_surface/__init__.py`

1. Write failing tests for immutable `ActionSlotPlan` and `ActionCandidate` plans compiled from
   registered operations in deterministic operation-name and Pydantic field order.
2. Add an inert `@action(operation=..., rel=..., description=...)` decorator and failing tests that
   compile only decorated functions found in class dictionaries across the MRO.
3. Use a descriptor that raises on access to prove compilation and safe-value collection never
   evaluate properties or arbitrary descriptors.
4. Require method slots from `inspect.signature`, excluding `self`, preserving annotations/defaults,
   and rejecting variadic, unannotated, and unknown-operation candidates with stable errors.
5. Run the focused suite and observe failure because action compilation is absent.
6. Implement compilation using `OperationRegistry`, `type(instance).__mro__`, each class
   `__dict__`, `inspect.signature`, and Pydantic `model_fields`; do not use `dir` or broad `getattr`.
7. Export the compiler/decorator API, run focused tests, Ruff, and mypy, then commit as
   `feat: compile explicit action candidates`.

### Task 3: Publish actions through explicit policy and safe binding

**Files:**
- Modify: `src/agent_surface/actions.py`
- Create: `tests/test_action_publisher.py`
- Modify: `src/agent_surface/__init__.py`

1. Write failing tests proving publication requires a policy and `DenyAllActions` emits nothing;
   `AllowActions` permits only named operations.
2. Require binding precedence: explicit values, exact-name compatible safe instance fields,
   defaults, then unbound typed slots. Prove a same-type field with the wrong name never binds.
3. Require safe instance data to come only from `vars(instance)` plus declared Pydantic fields.
   Reuse the raising descriptor fixture to prove publication does not evaluate it.
4. Test canonical scalar argv tokens and custom reference binding. The command token must be the
   codec ID, while `Action.bound` carries `{kind, id, label}`.
5. Require `MissingReferenceCodec` for a bound custom object with no codec—never call `str(object)`.
6. Require unresolved values to produce `command_template` placeholders and typed `slots`; attach
   an explicit paginated source action to a slot without expanding its choices.
7. Implement `ActionPublisher` with a required policy argument, strict exact-name compatibility,
   operation-name argv projection, and reference/scalar encoding.
8. Run focused tests, Ruff, and mypy; commit as `feat: publish policy-gated actions`.

### Task 4: Page bounded action discovery

**Files:**
- Modify: `src/agent_surface/actions.py`
- Create: `tests/test_action_catalog.py`
- Modify: `src/agent_surface/__init__.py`

1. Write failing tests for deterministic `ActionCatalog.page()` output using
   `OutputBudget.max_items`, exact `total`/`returned`/`truncated`, and one concrete `discover` action.
2. Require opaque versioned URL-safe cursors, stable `invalid_action_cursor` errors for malformed,
   wrong-version, and out-of-range inputs, and an immediate-next-page command only.
3. Build a 400-action fixture and follow successive cursors to prove every action is reachable once,
   no page exceeds the item budget, and no page enumerates later continuations.
4. Render the first page inside a `SuccessEnvelope` with default YAML options; require the complete
   response to fit 65,536 UTF-8 bytes and round-trip without an ellipsis placeholder.
5. Implement the minimal immutable catalog, cursor codec, and page construction using the existing
   `ActionCollection` validation.
6. Run focused tests, Ruff, and mypy; commit as `feat: add bounded action catalog`.

### Task 5: Publish adoption guidance and complete issue #4

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/adoption.md`
- Modify: `tests/test_repository_metadata.py`

1. Add a failing metadata test requiring public guidance for `ReferenceCodec`, `@action`, explicit
   policy, exact-name binding, `ActionCatalog`, immediate continuation, and no `str(object)` identity.
2. Add concise README examples showing one custom codec and one bounded action page. Extend adoption
   guidance without naming or linking any external consumer.
3. Add agent instructions forbidding property/descriptor evaluation, permissive publication, and
   exhaustive action expansion.
4. Run metadata tests, all focused action/reference tests, and `make check`.
5. Verify new public material has no external consumer name, organization, URL, or copied identifier.
6. Commit as `docs: publish bounded action discovery contract`.
7. Request independent code review; address each Critical/Important finding with a failing regression
   test and rerun `make check`.
8. Fast-forward `main`, rerun `make check`, push, watch GitHub Actions, and close issue #4 only after
   Python 3.12–3.14 and distribution jobs pass.

