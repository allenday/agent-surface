# MCP v2 contract

`MCPAdapter` projects the typed operation registry directly through the official MCP Python SDK.
It does not invoke Click, parse argv, or duplicate domain behavior.

Install the optional dependency and construct the adapter at an integration boundary:

```bash
pip install 'agent-surface[mcp]'
```

```python
from agent_surface.adapters.mcp import MCPAdapter

adapter = MCPAdapter(app, references=references, action_provider=actions)
```

For one public surface built from independent typed Apps, use `ComposedApp` directly. Its mounted
public paths become MCP tool names, while each child retains its own schemas and handler:

```python
from agent_surface import ComposedApp

surface = ComposedApp("infralink").mount("catalog", catalog_app)
adapter = MCPAdapter(surface)
```

Mount-specific MCP settings belong in `mcp={...}`; Click settings belong in `click={...}`. The
two option mappings never cross a transport boundary.

## One server for multiple typed surfaces

When an application is migrating operation families independently, compose existing adapters
instead of adding a second MCP transport or reflecting another command tree. The outer adapter owns
one SDK server; each tool call is dispatched to its source adapter, so that adapter retains its own
reference codecs, action provider, renderer, output budget, confirmation gate, and error policy.

```python
from agent_surface.adapters.mcp import MCPAdapter

catalog_mcp = MCPAdapter(catalog_app(), references=catalog_references)
operations_mcp = MCPAdapter(operations_app(), action_provider=operations_actions)
mcp = MCPAdapter.compose("infralink", catalog_mcp, operations_mcp, version="1.0.0")

await mcp.run_stdio()
```

`compose()` lists the union of source tools in lexical order. Its `page_size` is a single global
discovery bound for the composed server; source adapter page sizes do not apply. Duplicate tool
names are rejected at composition time with `ValueError` rather than being selected by order.
Composition is for public typed adapters only: do not mount Click commands, private runtime helpers,
or another MCP server behind it.

## Tool discovery

Each registered operation becomes one native MCP tool with its exact dotted name. Its description
is the operation summary. The input schema comes from the Pydantic request model in validation mode;
the output schema describes the structured success outcome. Tool annotations map the operation's
read-only, destructive, idempotent, and open-world metadata without inference.

Discovery is deterministic and cursor-paginated. A page returns at most 20 tools by default; pass a
positive `page_size` to `MCPAdapter` to choose another bound. The wire response uses `nextCursor`
when another page exists. Cursors are opaque, versioned tokens. Malformed, stale, and out-of-range
cursors are rejected rather than guessed.

## Calls and outcomes

Calls dispatch directly through `OperationRegistry.invoke()`, so sync and async handlers share the
same validation and output checks as direct Python and Click invocation.

The authoritative result is MCP `structuredContent`. Without an application-owned canonical
envelope renderer, a success has:

```yaml
{schema_version: '1', ok: true, result: {}, next_actions: {items: [], total: 0, returned: 0, truncated: false}}
```

Expected failures set `isError: true` and return a stable error code, message, optional repair
guidance, and bounded `next_actions` in `structuredContent`. Unexpected exceptions become a generic
`internal_error`; private exception text is not exposed. A text content item carries a bounded YAML
rendering of the same public outcome for compatibility with clients that do not display structured
content.

When `MCPAdapter(..., envelope_renderer=renderer)` is configured, `renderer.output_model` is the
tool output schema and `structuredContent` is the document produced from the operation, validated
public request view, outcome, bounded action frontier, and output budget. Sensitive input fields
are redacted before the view reaches the renderer. Use the same renderer for
`ClickAdapter` to retain one application-owned response normal form across both transports.

References are decoded only through an explicitly registered `ReferenceCodec`; incidental
`str(object)` conversion is never used. An exact registered reference field is advertised as a
string token in the MCP input schema, matching the value the codec accepts. Codec rejection becomes
a non-leaking `invalid_reference` error. Sensitive request fields and their lexical values are
recursively redacted from handled errors.

The output byte budget covers the combined YAML text and compact JSON encoding of
`structuredContent`, excluding MCP/JSON-RPC framing owned by the SDK. It defaults to 65,536 bytes.
MCP adapters reject budgets below 1,024 bytes so a complete structured size error remains
representable; oversized successful or error outcomes are replaced by that bounded error.

## HATEOAS actions

`next_actions` is a bounded, relevant frontier rather than the whole reachable graph. For a concrete
MCP transition, call the action's `operation` with its `bound` mapping:

```python
action = result.structured_content["next_actions"]["items"][0]
next_result = await client.call_tool(action["operation"], action["bound"])
```

The same action may carry a `command` for Click. Those are sibling projections of one transition,
not instructions for MCP to invoke a shell.

## Confirmation and safety

A destructive tool's schema requires `confirm: true`. Calls without that exact boolean return
`confirmation_required` before the handler runs. If the domain request already declares a boolean
`confirm` field, the value is passed through; otherwise it remains transport metadata and is removed
before Pydantic validation. MCP safety annotations are descriptive and do not replace this runtime
gate.

## Runtime transports

Use the native server directly in integration tests:

```python
from mcp import Client

async with Client(adapter.server, raise_exceptions=True) as client:
    tools = await client.list_tools()
```

Serve the same adapter over stdio:

```python
await adapter.run_stdio()
```

Or obtain the SDK-owned Streamable HTTP ASGI application:

```python
asgi_app = adapter.streamable_http_app(stateless_http=True, json_response=True)
```

The MCP SDK owns framing and transport lifecycle. Application code owns operations, references,
actions, and policies. See the [Python API](python-api.md), [CLI contract](cli-contract.md), and
[bookstore tutorial](../tutorials/bookstore.md).

The repository's executable [`examples/bookstore-mcp`](../../examples/bookstore-mcp) is a complete
stdio integration example. It shares persistent SQLite state with the bookstore CLI through
`AGENT_SURFACE_BOOKSTORE_DB`; the tutorial includes ready-to-adapt Codex and Claude Code entries.
