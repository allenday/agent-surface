# Native MCP v2 Adapter Design

## Purpose

Project the same typed operation registry as native MCP v2 tools. Consumers define no duplicate MCP
schemas and do not call their own CLI through a test runner, argv, or a JSON round trip. The adapter
targets application authors who need typed tool schemas, stable structured results, bounded tool
discovery, and direct domain invocation.

## Chosen approach

Use the official MCP v2 low-level server API. Supplying tool schemas directly from registered
Pydantic models is more robust than manufacturing Python signatures for high-level decorators and
preserves exact dotted operation names. A single generic `invoke` tool is rejected because it loses
native names, annotations, and per-operation schemas.

The optional dependency remains `mcp>=2,<3`. Importing `agent_surface` or its Click adapter never
requires MCP; importing the MCP adapter without the extra raises a concise installation error.

## Architecture

```text
Pydantic models + OperationRegistry
               |
         MCP tool compiler
          /           \
 paginated tools/list  tools/call
                           |
                 OperationRegistry.invoke
```

`MCPAdapter` accepts the same reference registry, bounded action provider, and output budget concepts
as `ClickAdapter`. The MCP module does not import Click, and the Click module does not import MCP.

## Tool projection

Each operation becomes one native tool with its exact stable dotted name:

```text
books.search
books.inspect
holds.create
holds.cancel
```

For each tool:

- `description` is the operation summary
- `inputSchema` is `input_model.model_json_schema(mode="validation")`
- `outputSchema` describes the shared success payload with the operation result model
- read-only, destructive, idempotent, and open-world metadata become MCP tool annotations
- exact registered reference types retain their Pydantic schema and are decoded by the shared
  reference registry before invocation when a token representation is used

The adapter calls `await app.operations.invoke(name, arguments)` directly. The SDK and the operation
registry may both validate inputs, but they use the same Pydantic schema and model; there is no
transport-specific business validation.

## Bounded discovery

Tool ordering is deterministic by exact operation name. `tools/list` uses opaque cursor pagination
with a configurable page size instead of returning an unbounded tool array. Cursors encode a version
and position and reject malformed or stale versions with stable errors.

Discovery is side-effect free. Calling a tool does not mutate tool visibility or create a
connection-specific working set. Clients follow `nextCursor` until complete. Contextual domain
actions remain bounded inside tool results through the shared action provider.

## Structured success

Successful calls return structured content:

```yaml
schema_version: "1"
ok: true
result: {book: {id: book_dune, label: Dune}, available: true}
next_actions:
  items:
    - rel: reserve
      command_template: [bookstore, holds, create, --book, "{book}", --confirm]
  total: 1
  returned: 1
  truncated: false
```

The MCP result's compatibility text content is a concise bounded YAML rendering of the same public
payload. Structured content is the authoritative machine value. MCP-native JSON transport does not
change the library's YAML-first human presentation policy.

## Errors and safety

Expected failures return `is_error=true` plus stable structured content:

```yaml
schema_version: "1"
ok: false
error: {code: book_not_found, message: Book was not found}
fix: Choose a reference returned by books.search.
next_actions: {items: [], total: 0, returned: 0, truncated: false}
```

Pydantic input errors map to `invalid_input`; domain `OperationError` fields are preserved;
unexpected failures become `internal_error` without traceback or secret leakage. Success output is
validated against the declared output schema.

MCP tool annotations are hints, not the enforcement boundary. Every destructive tool therefore also
requires an explicit `confirm: true` input at the adapter boundary. If the request model has a
compatible `confirm` field it receives `True`; otherwise confirmation is transport-only.

## Runtime and testing

The public adapter exposes the server object plus stdio and streamable-HTTP runners supported by the
official SDK. Initial scope tests the SDK's direct in-memory `Client(server)` path and one real stdio
subprocess; HTTP deployment behavior remains the SDK's responsibility.

Tests assert exact names, descriptions, input and output schemas, annotations, pagination, sync and
async calls, references, confirmation, bounded actions, structured domain errors, and semantic
equivalence with direct and Click invocation. Import-isolation tests prove the MCP adapter loads
without Click and the core package loads without the MCP extra.

## Primary references

- [MCP Python SDK v2 overview](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md)
- [MCP v2 tool schemas, annotations, and structured output](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/tools.md)
- [In-memory client testing](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/get-started/index.md)
- [Protocol tool-list pagination](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/draft/server/tools.mdx)
