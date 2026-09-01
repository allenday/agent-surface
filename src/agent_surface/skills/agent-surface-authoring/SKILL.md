---
name: agent-surface-authoring
description: Use when building or extending a Python application with agent-surface, especially when projecting Pydantic operations through Click and MCP with references, bounded HATEOAS actions, or YAML output
---

# Agent-Surface Authoring

## Overview

Build one typed operation registry and project it as sibling Python, Click, and MCP surfaces.
Keep the domain consumer-owned; `agent-surface` owns the integration boundary and transport contract.

Use `agent-friendly-cli-design` when deciding a general CLI contract. Use this skill when applying
that contract with this package.

## Environment preflight

Before writing or running an `agent-surface` integration:

1. Inspect the repository for its established Python environment and dependency workflow.
2. Check whether `agent_surface` imports in that environment.
3. If it is unavailable, explain the appropriate project-local installation, such as
   `pip install 'agent-surface[mcp]'`, and ask before changing the environment.
4. Verify the import in the chosen environment, then continue.

Do not choose or create a virtual environment, install globally, or change the project dependency
manager on the user's behalf. The user or repository owns that decision.

## Recipe

1. Put strict Pydantic request and result models beside a thin integration wrapper around the domain
   service. Do not make domain classes inherit transport types.
2. Create an `App`; register one `@app.operation` per stable dotted operation name. Keep handlers
   small and translate expected domain failures to `OperationError(code, message, fix=...)`. When
   a valid domain result needs a non-zero CLI exit, return `OperationOutcome(result, exit_code=...)`
   instead; MCP remains successful.
3. Register a `ReferenceCodec` for every non-scalar object used in a request, result, or action.
   Encode a stable wire identifier, decode it explicitly, and never rely on `str(object)`.
4. Return state-appropriate actions through an explicit provider and `AllowActions` policy. Every
   action needs a `rel`, a concrete description, and only bound values that stringify safely.
5. Bound lists, payload bytes, and action frontiers. Use a continuation or discovery action for high
   branch factor; never serialize every reachable state or silently truncate.
6. Project the same app with `build_click_group(app)` and `MCPAdapter(app)`. Do not reflect the
   Click tree into MCP or implement a second operation registry.
7. Give every write an explicit confirmation field; mark read-only operations accurately.

Read [reference.md](reference.md) for the implementation skeleton and verification matrix.

## Definition of Done

- Pydantic validation, domain behavior, references, actions, and `OperationError` behavior have
  focused tests.
- Click YAML envelopes and MCP tool schemas/invocations exercise the same operation.
- Pagination and output budgets expose truthful `total`, `returned`, `truncated`, and a next step.
- A built wheel includes this skill and its sidecar; source and installed resources both resolve.

## Common Mistakes

| Mistake | Fix |
| --- | --- |
| Domain model used as an opaque command value | Register a stable `ReferenceCodec` |
| Action inferred from arbitrary methods | Use explicit provider and `AllowActions` |
| Separate Click and MCP handlers | Project both from one `App` |
| All actions or list items emitted | Publish a bounded frontier with discovery |
| Domain exception leaks to a transport | Translate it to `OperationError` |
| Write looks safe because it is only a CLI flag | Require a modelled confirmation field |
