# Typed app composition

Use `ComposedApp` when one public surface needs operations from independently typed applications.
Each mounted `App` keeps its own request models, shared inputs, reference codecs, action policy, and
canonical renderer. Composition supplies the public command and tool namespace; it does not merge
the child schemas.

The executable [composition example](../../examples/composition.py) builds a surface with both
Click and MCP projections.

The public CLI paths are `diagram ...` and `project ...`; MCP tool names use the same
dot-separated paths. A field shared by `diagram_app` is accepted only by its operations. It is not
silently inherited by `project_app`.

Mount paths and child operation names must be non-empty segments. `click` and `mcp` options are
explicitly scoped to their projection, so transport settings never leak between adapters. MCP tool
pagination is global to `MCPAdapter(surface, page_size=...)`, not a mount setting. Duplicate paths and a path that
would be both an operation and a namespace are rejected while building the composed surface. See
the [Python API reference](../reference/python-api.md) for projection options and the
[MCP contract](../reference/mcp-contract.md) for wire behavior.
