# Reference Consumer Conformance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a generic, reusable acceptance fixture proving that a demanding consumer can adopt agent-surface without importing it into domain modules.

**Architecture:** A consumer-owned `domain.py` defines Pydantic models, errors, and services. A separate `integration.py` is the only layer that imports agent-surface, registers service wrappers, translates errors, and attaches operation metadata; adapter issues reuse the same fixture.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, agent-surface operation registry

### Task 1: Define the consumer-owned domain fixture

**Files:**
- Create: `tests/reference_consumer/__init__.py`
- Create: `tests/reference_consumer/domain.py`
- Create: `tests/test_reference_consumer.py`

1. Write a failing test that imports the domain fixture, inspects its source, and rejects any `agent_surface` import.
2. Require consumer-owned models for lookup, bounded listing, destructive mutation, stable references, and sensitive input metadata.
3. Run `.venv/bin/pytest tests/test_reference_consumer.py -v` and confirm failure because the fixture is absent.
4. Implement the minimal domain models, exceptions, and in-memory sync/async service.
5. Run the focused test and commit the domain fixture.

### Task 2: Register the integration boundary

**Files:**
- Create: `tests/reference_consumer/integration.py`
- Modify: `tests/test_reference_consumer.py`

1. Add failing tests for three operations: read-only lookup, async bounded list, and destructive mutation.
2. Assert that operation definitions retain consumer model types and safety metadata.
3. Assert that the integration layer translates a consumer exception to a stable `OperationError` code.
4. Register thin wrappers in `integration.py`; keep business logic in the domain service.
5. Run focused and full tests, then commit the integration fixture.

### Task 3: Publish the adoption contract

**Files:**
- Create: `docs/adoption.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `tests/test_repository_metadata.py`

1. Add a failing repository-metadata test requiring an adoption guide linked from README and agent instructions.
2. Document the domain/integration/transport boundary, error translation, sensitivity metadata, and staged adapter migration.
3. State that consumers own their Pydantic models and must not route one transport through another.
4. Run metadata tests and `make check`.
5. Verify the fixture and new docs contain no external source name, organization, URL, or copied identifier.
6. Commit, push, link the implementation to GitHub issue #2, and close the issue only after CI passes.
