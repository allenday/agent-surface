---
name: agent-friendly-cli-design
description: Use when designing or extending command-line tools that agents must use reliably, especially when machine-readable output, command contracts, output budgets, or discoverable next actions must remain predictable
---

# Agent Friendly CLI Design

## Overview

Design stable, bounded, machine-readable CLI work products for agents. Define the command surface, response contract, repairable errors, discovery, and output limits.

## When to Use

Use this skill when creating or extending a CLI, redesigning agent-facing output, exposing parsed input or next actions, or controlling high-branch-factor responses.

Do not use it for implementation of an already-approved command contract or packaging-only changes.

## Required Design Artifact

Every design must include:
- purpose and intended users
- command tree
- machine-readable success and error contracts
- output-size and truncation policy
- discovery/help strategy
- 2 to 4 representative commands

Read [reference.md](reference.md) when drafting concrete envelopes.

## Command Contract

Machine-readable output is the default. Human rendering is optional; prose-only output fails the contract.

At minimum include:
- `ok`
- `command.raw` as the original argv sequence, not a reconstructed shell string
- shallow `command.parsed` with path, bound args/options, and flags
- `result` or `error`
- `next_actions`

Keep the parsed view close to parser truth. Add `command.resolved`—executable, version, cwd, and config source—when environment ambiguity is plausible.

## Bounded Progressive Disclosure

`next_actions` is a bounded, relevant frontier, not an exhaustive serialization of the reachable action graph.

- Emit a small set of immediately useful, concrete actions.
- For high branch factor, return collection metadata such as `total`, `returned`, and `truncated`, plus a concrete discovery action.
- Represent homogeneous actions with a parameterized template and a discoverable parameter source instead of enumerating every binding.
- For pagination, expose the immediate continuation; do not enumerate every page.
- Never truncate silently.

Completeness means every omitted action remains discoverable, not that every reachable action appears in one response. Each design must set item and byte limits with escalation paths.

## Output-Size Policy

Specify separate handling for:
- result lists and pagination
- logs
- nested detail
- `next_actions`
- total response bytes

Prefer terse defaults with explicit detail, cursor, filter, or discovery commands. If output cannot be safely bounded, return a structured size error rather than partial unmarked data.

## Errors and Discovery

Errors must include a stable code, clear message, fix guidance when possible, and useful next actions. Explain how agents discover commands, arguments, schemas, continuations, and additional actions through machine-readable commands as well as normal help.

## Common Mistakes

| Mistake | Fix |
| --- | --- |
| “Supports YAML/JSON” without an envelope | Define the concrete contract |
| Raw command reconstructed as text | Preserve argv boundaries |
| Deep parser internals | Keep the parsed view shallow |
| Every reachable action emitted | Bound the frontier and expose discovery |
| Unlimited or silent truncation | Declare budgets and continuation metadata |
| Prose-only failure | Return a repair-oriented error contract |
