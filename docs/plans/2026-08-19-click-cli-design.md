# Generated Click CLI Design

## Purpose

Generate an agent-first Click command tree from `App.operations` without requiring consumers to
maintain a second transport-specific command model. The adapter is intended for Python application
authors who want a mountable CLI, stable structured output, and the same Pydantic validation and
domain behavior used by direct invocation.

The CLI remains comfortable for humans: normal `--help` is concise Click help, command names are
predictable, and errors explain how to recover. Machine discovery uses bounded structured commands.

## Architecture

`ClickAdapter` compiles immutable `CliCommandPlan` and `CliFieldPlan` values from registered
operations. The plans capture command topology and lossless lexical conversion; they do not contain
business logic. Generated callbacks build a payload and call `OperationRegistry.invoke()` directly.

```text
Pydantic models + OperationRegistry
               |
        Click plan compiler
               |
       generated click.Group
               |
      OperationRegistry.invoke
```

The adapter accepts an `App`, an optional `ReferenceRegistry`, an explicit bounded action provider,
render options, and an argv provider. The default action provider returns no contextual actions.
Publication never becomes permissive merely because candidates exist.

`build_click_group(...) -> click.Group` is the public convenience API. Consumers can call the group
directly or mount it beneath an existing Click group.

## Command tree and reserved names

Dotted operation names become nested Click paths:

```text
bookstore
├── books
│   ├── search
│   └── inspect
├── holds
│   ├── create
│   └── cancel
├── operations
│   ├── list [--cursor CURSOR] [--limit N]
│   └── describe NAME
└── actions
    ├── list [--cursor CURSOR] [--limit N]
    └── explain OPERATION
```

`operations` and `actions` are reserved generated namespaces. Adapter construction fails with a
stable `cli_command_conflict` if an operation would collide with a generated command or if one
operation is both a leaf and a group prefix.

Representative commands:

```bash
bookstore operations list --limit 20
bookstore books search --query dune --limit 2
bookstore books inspect --book book_dune
bookstore holds create --book book_dune --confirm
```

## Field projection

Fields are named options by default. A positional argument requires explicit Pydantic metadata:

```python
Field(json_schema_extra={"cli": {"kind": "argument"}})
```

The compiler supports:

- strings, integers, finite floats, and optional forms
- `--flag/--no-flag` booleans
- repeated scalar options for lists, sets, and tuples
- `Enum`, `StrEnum`, and `Literal` choices
- lexical `Path` values without eager resolution
- custom values whose exact type has a registered `ReferenceCodec`

Click handles syntax and lossless conversion. Pydantic remains authoritative for numeric bounds,
lengths, model validators, strictness, and defaults. Arbitrary nested models without a reference
codec fail adapter construction with `unsupported_cli_field`; the adapter never stringifies them or
quietly accepts an ambiguous document fragment.

Sensitive fields use `json_schema_extra={"sensitive": True}`. They are hidden from shell completion
where practical and always redacted from parsed command views and error details.

## Invocation and argv preservation

The generated root captures `(prog_name, *args)` before Click parses or normalizes anything. That
tuple becomes `command.raw`; it is never reconstructed from parsed values. `command.parsed` is a
shallow parser-truth view containing the command path, positional arguments, options, and boolean
flags. Resolved executable, version, cwd, and config data are optional.

Callbacks decode registered reference tokens, construct a payload, enforce the safety gate, and
await `OperationRegistry.invoke()`. Sync and async handlers therefore use the same invocation path as
library callers.

## Safety gates

Every `destructive=True` operation requires adapter-level `--confirm`. If the input model has a
compatible boolean field named `confirm`, successful confirmation also binds that field to `True`.
Otherwise confirmation remains transport-only and is not added to the consumer payload.

Missing confirmation returns `confirmation_required` with exit code 3. A Click callback never calls
the handler before this gate passes.

## Success contract

YAML with adaptive flow style is the default:

```yaml
schema_version: "1"
ok: true
command:
  raw: [bookstore, books, inspect, --book, book_dune]
  parsed:
    path: [books, inspect]
    args: {}
    options: {book: book_dune}
    flags: []
result: {book: {id: book_dune, label: Dune}, available: true}
next_actions:
  items:
    - rel: reserve
      command: [bookstore, holds, create, --book, book_dune, --confirm]
  total: 1
  returned: 1
  truncated: false
```

`--format yaml|json` and `--yaml-style auto|flow|block` are shared leaf-command options. Rendering
uses the shared `RenderOptions` and does not change semantics.

## Error contract and exit codes

Expected errors emit a complete machine-readable envelope on stdout. Concise diagnostics may be
written to stderr; tracebacks and secrets never enter either stream.

```yaml
schema_version: "1"
ok: false
command:
  raw: [bookstore, books, inspect, --book, missing]
  parsed:
    path: [books, inspect]
    args: {}
    options: {book: missing}
    flags: []
error: {code: book_not_found, message: Book was not found}
fix: Choose a reference returned by books.search.
next_actions:
  items:
    - rel: search
      command: [bookstore, books, search, --query, missing]
  total: 1
  returned: 1
  truncated: false
```

Stable exit mapping:

- 0: success and discovery
- 2: Click syntax or Pydantic input validation
- 3: confirmation or policy denial
- 4: expected domain `OperationError`
- 70: unexpected handler, output-validation, or rendering failure

Unknown commands, missing options, and bad lexical values retain the original argv and include a
concrete `operations describe` recovery action.

## Bounded help and discovery

`--help` stays human-oriented. `operations list`, `operations describe`, `actions list`, and
`actions explain` are the machine-readable discovery contract. List commands are deterministic and
cursor-paginated. Defaults are 20 items and 65,536 UTF-8 bytes. Truncated responses include totals
and exactly one immediate continuation. Oversized documents become `response_too_large`; the
renderer never silently slices data or inserts ellipses.

## Testing

Tests exercise generated routing, mounting, raw argv, parsed views, sync and async handlers,
Pydantic validation equivalence, booleans, repeated values, enums, literals, paths, explicit
references, secret redaction, destructive gates, error exits, structured discovery, and output
budgets. The reference consumer must execute through Click without importing Click in its domain
module or adding transport-specific business logic.

The bookstore documentation example is executable and uses the real generated adapter.

