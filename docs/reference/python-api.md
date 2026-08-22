# Python API

The public surface is organized around a few concepts:

| Type | Purpose |
| --- | --- |
| `App` | register and directly invoke typed operations |
| `OperationError` | stable expected failure with repair guidance |
| `ReferenceCodec`, `ReferenceRegistry` | encode, decode, and display domain references |
| `Action`, `ActionCatalog`, `AllowActions` | describe and authorize bounded next steps |
| `BoundedCollection`, `OutputBudget` | make omission and continuation explicit |
| `RenderOptions`, `render`, `render_envelope` | deterministic adaptive YAML or JSON |
| `ClickAdapter`, `build_click_group` | project the registry into a mountable Click tree |
| `MCPAdapter` | project the registry into native MCP v2 tools and transports |
| `CanonicalEnvelopeRenderer`, `Invocation` | preserve an application's existing response normal form across adapters |

Operations accept one Pydantic request model and return one declared result model. Both synchronous
and asynchronous handlers use the same registry:

```python
@app.operation("books.search", summary="Search books", read_only=True)
async def search(request: SearchRequest) -> SearchPage:
    return await service.search(request)
```

Use `app.invoke("books.search", request)` for direct Python calls. Build a CLI with
`build_click_group(app, references=references, action_provider=actions)`. Adapters are sibling
projections; handlers never import Click or MCP.

MCP is an optional dependency:

```bash
pip install 'agent-surface[mcp]'
```

Import `MCPAdapter` from `agent_surface.adapters.mcp`, then use `.server` for embedding or in-memory
tests, `await .run_stdio()` for stdio, and `.streamable_http_app()` for ASGI. See the
[MCP contract](mcp-contract.md).

## Canonical application envelopes

An application with an established public response document can provide a
`CanonicalEnvelopeRenderer` to both adapters. Its `render()` method receives the registered
operation, a JSON-compatible public request view when available, result or `OperationError`,
bounded next actions, and the active output budget. Fields declared `sensitive` are always
redacted before this view reaches the renderer. Its declared `output_model` becomes the MCP tool
output schema.

The renderer owns only document shape. `agent-surface` continues to own parser validation,
reference decoding, confirmation, action selection, redaction, and output budgeting. If the first
rendered document exceeds its byte budget, the renderer is called again with no request, result,
or next actions and a `response_too_large` error. Pass the same renderer to `ClickAdapter` and
`MCPAdapter` to preserve one application-owned normal form; do not add a transport-specific
wrapper.

The package is pre-1.0. Prefer an internal integration module so consumer code owns its domain types
and the projection can evolve without leaking library types throughout the application. See
[adopting an existing app](../how-to/adopt-an-existing-app.md).
