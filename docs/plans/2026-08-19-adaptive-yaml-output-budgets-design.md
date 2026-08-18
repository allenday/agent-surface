# Adaptive YAML and Output Budgets Design

## Purpose and users

Agent-surface needs a deterministic human-readable representation for developers and agents without
allowing a response to consume unbounded terminal or model context. YAML is the default
representation because it remains fully structured while being easier to scan than JSON. JSON is an
explicit alternate representation for consumers that require it.

This design adds a transport-neutral rendering layer. Generated Click and MCP adapters will consume
the same models later; this issue does not implement either adapter.

## Design choices

The library will combine adaptive presentation with explicit collection semantics:

- `auto` YAML uses flow style for small leaf mappings and sequences that fit on one line.
- `flow` and `block` force stable whole-document presentation styles.
- Multiline strings remain block scalars in `auto` and `block` modes.
- Unicode is emitted directly and values round-trip through a safe YAML loader.
- Mapping order follows the source model or mapping. Keys are never reordered by the renderer.
- JSON remains available through the same renderer interface.
- The renderer never inserts ellipsis placeholders and never silently removes values.

Adaptive style is a presentation decision only. Pagination and discovery remain producer-owned
semantics.

## Components

### Render options and budgets

`OutputBudget` is an immutable Pydantic contract with stable defaults:

- `max_items: 20`
- `max_bytes: 65_536`, measured after UTF-8 encoding

`RenderOptions` selects `format` (`yaml` or `json`), `yaml_style` (`auto`, `flow`, or `block`), and an
`OutputBudget`. Auto-style thresholds remain library policy rather than public tuning knobs for the
first release: a leaf collection is eligible for flow style when it has at most six entries, contains
no multiline scalar, and its isolated YAML representation fits within 100 columns.

### Explicit bounded collections

`BoundedCollection[T]` carries:

- `items`
- `total`
- `returned`
- `truncated`
- `continuation`, an `Action` required exactly when `truncated` is true

`BoundedCollection.from_sequence(...)` may slice a sequence only when the caller supplies a real
continuation action. Without one, exceeding `max_items` raises `OutputBudgetExceeded` with stable
code `item_budget_exceeded`. No placeholder item is inserted.

Existing `ActionCollection` retains its action-specific `discover` field and validation. Render-time
item validation recognizes both collection contracts but does not mutate them.

### Renderer

`render(value, options=RenderOptions()) -> str` accepts Pydantic models and JSON-compatible Python
values. It derives exact exemption paths for structural argv, parser-path, flag, and action-command
sequences on typed contracts, converts models to JSON-compatible values, then validates every other
serialized collection against the item budget. This ordering includes collections created by Pydantic
field serializers without making command metadata consume the domain item budget. Serialization is
deterministic, and the low-level function raises `OutputBudgetExceeded` rather than returning partial
data.

`render_envelope(envelope, options=RenderOptions()) -> str` is the adapter-ready entry point. If an
item or byte budget is exceeded, it renders a compact `ErrorEnvelope` with the original command,
stable limit code, structured measurements, and recovery guidance. If even that error cannot fit an
extremely small configured byte budget, it raises the original exception rather than emitting an
invalid or partial contract.

### Errors

`OutputBudgetExceeded` exposes:

- `code`: `item_budget_exceeded` or `response_too_large`
- `message`: stable human-readable summary
- `details`: JSON-compatible measurements and paths
- `fix`: guidance to use a lower limit, narrower detail level, or continuation command

Configuration values below one item or one byte are rejected by Pydantic validation. A budget error
never returns a partially serialized document.

## Data flow

1. Domain code returns its consumer-owned Pydantic result.
2. The integration layer wraps bounded result sequences with a concrete continuation action.
3. A future CLI or MCP adapter constructs the success or error envelope.
4. `render_envelope` converts the envelope to JSON-compatible data.
5. Item validation rejects unbounded over-budget collections.
6. YAML or JSON serialization produces a complete document.
7. The byte budget accepts the complete document or substitutes a compact structured error envelope.

## Planned command tree and discovery

Generated CLIs will project renderer controls consistently across operations:

```text
<app> <operation> [arguments]
  --format yaml|json
  --yaml-style auto|flow|block
  --max-items INTEGER
  --max-bytes INTEGER

<app> actions list [--cursor CURSOR] [--limit INTEGER]
<app> help --format yaml|json
```

Normal `--help` remains available for people. Machine-readable help and action discovery will return
the same bounded envelopes as normal commands. A truncated result exposes its immediate continuation;
a high-branch-factor action frontier exposes `actions list`. Discoverability means every omitted
item or action remains reachable, not that the full graph appears in one response.

Representative future commands:

```text
inventory resource list --limit 20
inventory resource list --cursor resource-020 --yaml-style flow
inventory resource inspect resource-017 --format json
inventory actions list --for-state state-7c91 --limit 20
```

## Success and error contracts

The existing `SuccessEnvelope` and `ErrorEnvelope` remain the machine-readable outer contracts. A
bounded result appears as normal structured data:

```yaml
ok: true
result:
  items: [{ref: resource-001}, {ref: resource-002}]
  total: 40
  returned: 2
  truncated: true
  continuation: {rel: next-page, command: [inventory, resource, list, --cursor, resource-002]}
next_actions: {items: [], total: 0, returned: 0, truncated: false}
```

`render_envelope` translates `OutputBudgetExceeded` to a normal error envelope:

```yaml
ok: false
error:
  code: response_too_large
  message: Rendered response exceeds the byte budget
  details:
    - {path: [], code: response_too_large, value: {measured_bytes: 70211, max_bytes: 65536}}
fix: Retry with a lower item limit or a narrower detail level.
next_actions: {items: [], total: 0, returned: 0, truncated: false}
```

## Testing

Golden and semantic tests will cover:

- auto-style flow decisions for small leaf dictionaries and lists
- forced flow and block modes
- Unicode and multiline strings
- nested Pydantic models
- YAML and JSON round trips
- exact byte-budget boundaries using UTF-8 byte counts
- marked bounded collections and required continuation actions
- rejection of raw oversized collections
- absence of ellipsis placeholders
- package exports, typing, lint, wheel smoke testing, and Python 3.12–3.14 CI
