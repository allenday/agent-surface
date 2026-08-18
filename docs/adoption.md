# Adoption Boundary

Adopt `agent-surface` at an integration layer. Keep domain models, exceptions, services, and
policies consumer-owned; they should not import the library or inherit its transport contracts.

```text
consumer domain → agent-surface integration → CLI / MCP / schemas
```

## Domain layer

Domain code may use its own Pydantic request and result models. It owns validation that expresses
business meaning, including bounded page semantics and confirmation requirements. Annotate a
sensitive field with explicit schema metadata when adapters must redact it:

```python
access_token: str = Field(repr=False, json_schema_extra={"sensitive": True})
```

Domain services raise consumer exceptions. They do not construct command envelopes, MCP results,
or `OperationError` instances.

## Integration layer

The integration layer creates an `App`, registers thin typed wrappers around domain services, and
attaches surface policy such as `read_only`, `destructive`, `idempotent`, and `open_world`.
Wrappers translate expected consumer exceptions into stable `OperationError` codes and repair
guidance. They do not reproduce business logic.

The models referenced by handler signatures remain consumer-owned. The registry retains those
models today. The planned adapter contract is to inspect them when generating transport inputs so
applications will not need parallel Click or MCP schemas. Until those adapters ship, retain
existing transport schemas and remove them only after parity is proven.

## Transport layer

CLI and MCP adapters will be sibling projections of the operation registry. Never implement one
transport by invoking, parsing, or reflecting the other. This preserves Pydantic constraints,
argv boundaries, structured errors, safety metadata, and asynchronous execution without string
round-trips.

## Staged migration

1. Register existing service methods behind an internal integration module.
2. Verify direct invocation and stable error translation.
3. Add the YAML/CLI projection while retaining golden output tests.
4. Add native MCP tools from the same registry and compare semantic results.
5. Remove legacy transport-specific schema and dispatch code only after parity is proven.

The conformance fixture under `tests/reference_consumer/` demonstrates this boundary with entirely
synthetic data. It is the acceptance surface for future adapters.
