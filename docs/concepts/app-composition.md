# Typed app composition

Use `ComposedApp` when one public surface needs operations from independently typed applications.
Each mounted `App` keeps its own request models, shared inputs, reference codecs, action policy, and
canonical renderer. Composition supplies the public command and tool namespace; it does not merge
the child schemas.

```python
from agent_surface import ComposedApp
from agent_surface.adapters.click import build_click_group
from agent_surface.adapters.mcp import MCPAdapter

surface = (
    ComposedApp("infralink", version="0.2.0")
    .mount("diagram", diagram_app)
    .mount("diagram.project", project_app)
)
cli = build_click_group(surface)
mcp = MCPAdapter(surface)
```

The public CLI paths are `diagram ...` and `diagram project ...`; MCP tool names use the same
dot-separated paths. A field shared by `diagram_app` is accepted only by its operations. It is not
silently inherited by `project_app`.

Mount paths and child operation names must be non-empty segments. Duplicate paths and a path that
would be both an operation and a namespace are rejected while building the composed surface. See
the [Python API reference](../reference/python-api.md) for projection options and the
[MCP contract](../reference/mcp-contract.md) for wire behavior.
