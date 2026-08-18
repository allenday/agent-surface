# Agent Surface Design

## Purpose

`agent-surface` lets an application define typed operations once and project them as an agent-friendly CLI, MCP tools, and machine-readable schemas. It is intended for Python library and application authors who want transport adapters without duplicating validation, error, discovery, pagination, or action metadata.

The PyPI distribution and executable are named `agent-surface`; the import package is `agent_surface`.
The supported runtime is Python 3.12 and newer, developed and tested in an isolated virtual environment.

## Architecture

The source of truth is a registry of typed operations backed by Pydantic request and result models. Click and MCP are thin adapters. OpenAPI and JSON Schema are projections of the registry. Neither transport calls another transport.

```text
Pydantic types + operation metadata
               |
        OperationRegistry
          /     |      \
       Click   MCP    Schema export
          \     |      /
         shared invocation engine
```

An operation records its stable name, handler, input and output types, description, and safety annotations. Handlers return domain values or raise domain errors; adapters translate those outcomes into their native transport while preserving the shared contract.

## Reflective Action Synthesis

Reflection is opt-in. Only registered operations and methods decorated with `@action` are candidates. Class-level Pydantic `model_fields` and callable signatures are compiled into immutable plans; arbitrary attributes, properties, and descriptors are never scanned or evaluated.

At runtime an action candidate is published only when its signature is bindable, preconditions pass, policy permits it, referenced values have stable codecs, and the action fits the output budget. Binding precedence is explicit metadata, context injection, exact name plus compatible type, defaults, then an unbound typed slot. Type-only matching is disabled by default.

Collections become discoverable slot sources instead of Cartesian expansions. `next_actions` is a bounded relevant frontier; omitted actions remain available through a paginated discovery operation.

## References and Rendering

Object identity is separate from display text. A reference codec provides `encode`, `decode`, and `display`; CLI commands use the stable encoded token and structured output carries kind, id, and optional label. Python `str()` is never the identity contract.

YAML 1.2 is the CLI default. JSON and human renderers are optional projections. YAML defaults to `auto` style: small scalar collections use flow style, small documents may be entirely flow style, and larger structures use block layout. Explicit `block` and `flow` overrides remain available. Renderers never use ellipsis as an omission marker; pagination and truncation are explicit data.

## Command Contract

CLI success envelopes contain `schema_version`, `ok`, `command.raw` as argv, shallow `command.parsed`, `result`, and bounded `next_actions`. Errors contain a stable code, message, details, optional fix guidance, and bounded next actions. Expected failures use nonzero exit codes while retaining a machine-readable stdout envelope; diagnostics go to stderr.

Default output policies are configurable but concrete: bounded result items, action items, logs, nesting, serialized bytes, and YAML flow thresholds. Truncation is never silent.

## Command Tree

```text
agent-surface
├── operations list
├── operations describe NAME
├── actions list --for REF
├── actions explain OPERATION --for REF
├── schema operation NAME
├── schema json-schema
├── schema openapi
└── mcp serve --transport stdio|streamable-http
```

Applications normally expose their own generated root command; the framework command supports inspection, schemas, and MCP serving.

## Error Handling

Registration-time ambiguity fails early with codes such as `invalid_action_signature`, `ambiguous_slot_binding`, and `missing_reference_codec`. Invocation failures use `invalid_input`, domain-specific errors, or `internal_error`. Rendering failures use `response_too_large` or `unsupported_serialization_value`. MCP adapters report tool errors through MCP without leaking tracebacks.

## Testing

Contract tests exercise the same operation through direct invocation, Click, and MCP. Schema snapshots verify stable input/output contracts. Property-oriented tests cover reference-codec round trips, deterministic rendering, output budgets, absence of descriptor evaluation, and bounded high-branch-factor action discovery. Every behavior is implemented test-first.

## Deferred Scope

Protobuf and gRPC adapters are deferred until a real cross-language wire requirement exists. Authentication, persistent action-state storage, and a general HTTP runtime are also outside v0.1; the OpenAPI export remains sufficient groundwork for a later HTTP adapter.
