# Click Stdin Field Source Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let a sensitive Pydantic request field obtain one bounded value from stdin in the generated Click adapter, while MCP continues to use the ordinary typed field.

**Architecture:** `CliPlanCompiler` recognizes `json_schema_extra["cli"]["source"] == "stdin"` and stores explicit source metadata on the immutable field plan. Click suppresses the normal value option and adds a generated `--<field>-stdin` presence flag. Invocation reads and validates one UTF-8 line only when that flag is supplied, then injects the typed string into the existing shared payload path before Pydantic validation.

**Tech Stack:** Pydantic metadata, Click, pytest, YAML/JSON error envelopes.

### Task 1: Specify the field-plan contract

**Files:**
- Modify: `tests/test_click_plans.py`
- Modify: `src/agent_surface/adapters/click.py`

1. Add failing compiler tests for a sensitive string stdin field, its generated flag, and invalid metadata.
2. Run the focused plan tests and observe the source-metadata failures.
3. Add the smallest immutable field-plan metadata and compiler validation.
4. Re-run focused plan tests.

### Task 2: Inject one bounded stdin value at invocation

**Files:**
- Modify: `tests/test_click_invocation.py`
- Modify: `src/agent_surface/adapters/click.py`

1. Add failing tests for successful piped input, missing, empty, multi-line, and oversized input.
2. Verify the new invocation tests fail because no generated flag/value source exists.
3. Add generated presence flag, single bounded binary read, newline normalization, and structured error mapping.
4. Re-run focused invocation tests.

### Task 3: Preserve transport and secrecy contracts

**Files:**
- Modify: `tests/test_click_invocation.py`, `tests/test_mcp_tools.py`, and relevant docs

1. Add failing tests that the source value never appears in raw/parsed envelopes or errors and MCP schema remains unchanged.
2. Implement only the redaction/description work required by those tests.
3. Run focused tests, then `make check`.
4. Commit, push, and report the exact public contract on issue #11 for customer feedback.
