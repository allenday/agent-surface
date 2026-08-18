# Adopt an existing application

Introduce `agent-surface` behind one internal adapter boundary. Keep domain models, services,
exceptions, and policy consumer-owned.

```text
domain service -> typed integration module -> Click / MCP / schemas
```

1. Create an `App` in the integration module.
2. Register thin typed wrappers around existing service methods.
3. Translate expected domain exceptions into stable `OperationError` values.
4. Register codecs for object references that cross the boundary.
5. Add an explicit action provider and publication policy.
6. Generate the Click surface alongside the legacy CLI; compare golden behavior before removal.
7. Project MCP from the same registry, never by reflecting the Click tree.

Do not make domain classes inherit transport types. Pydantic request and result models may remain in
the consumer package; the registry reads their declared fields and method signatures.

For a working integration, see [`examples/bookstore.py`](../../examples/bookstore.py). For the
architectural contract and staged migration details, read the original
[adoption boundary](../adoption.md).

