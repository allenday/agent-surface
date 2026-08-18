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

The package is pre-1.0. Prefer an internal integration module so consumer code owns its domain types
and the projection can evolve without leaking library types throughout the application. See
[adopting an existing app](../how-to/adopt-an-existing-app.md).
