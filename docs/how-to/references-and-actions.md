# References and actions

## Register stable references

Implement `ReferenceCodec[T]` when a model field contains a domain object whose command value is not
already a scalar. Its three responsibilities are deliberately separate:

- `encode(value)` returns the stable wire identifier;
- `decode(raw)` resolves an incoming identifier;
- `display(value)` supplies optional human-facing text.

Register the codec in a `ReferenceRegistry`. Exact-type lookup prevents accidental coercion, and no
fallback calls `str(object)`.

## Publish a relevant frontier

An action provider receives the completed operation and its result or error. Return only actions
that are useful and valid in that state. Use `ActionCatalog` when agents need to page or inspect the
larger candidate set.

For a high-branch-factor slot, publish one parameterized action with a discoverable source instead
of one command per possible value. For pagination, publish only the immediate continuation.

Candidate discovery and publication are separate. Registered operations and `@action` methods may
be introspected narrowly, but an explicit policy such as `AllowActions` decides what can reach
`next_actions`. Properties and arbitrary descriptors are never evaluated.

See [HATEOAS and bounded discovery](../concepts/hateoas.md) for the reasoning and the
[Python API reference](../reference/python-api.md) for the primary types.
