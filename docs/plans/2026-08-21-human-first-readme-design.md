# Human-first root README design

## Purpose

Make the root README a 30-second human on-ramp for a library that is intentionally agent-first in
its runtime contracts. Agents can follow linked contracts, tutorials, and the packaged skill; humans
should quickly understand the value, copy a working start, and choose a deeper path.

## Information flow

1. A HATEOAS-led promise: typed Python operations become HATEOAS CLI and MCP surfaces so callers do
   not guess commands, routes, or object encodings. Link HATEOAS to Roy Fielding's primary REST text
   and MCP to the official protocol introduction.
2. A 30-second library-adopter path: install, define one Pydantic operation, and project both Click
   and MCP from the same app registry.
3. A tiny trajectory: one compact YAML result with a concrete `next_actions` item and the command it
   enables. Keep the full bookstore journey in the tutorial.
4. Three reader paths: evaluate the idea, adopt in an application, or connect an agent.
5. A direct, prominent link to the shipped `agent-friendly-cli-design` `SKILL.md` for coding agents.
6. One short principles block and project links.

## Boundaries

The root README will not duplicate the full bookstore transcript, detailed Click/MCP contracts,
output-budget policy, reference-codec rules, release procedure, or client configuration. Those stay
in their existing linked documents. The rewrite changes documentation only; package behavior and
public APIs remain unchanged.
