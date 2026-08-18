# HATEOAS and bounded discovery

HATEOAS means Hypermedia as the Engine of Application State. In a web API, links in a response tell
a client which transitions are valid next. In `agent-surface`, a typed command array plays the same
role:

```yaml
result: {ref: {value: book_dune}, available: true}
next_actions:
  items:
  - rel: reserve
    command: [bookstore, holds, create, --book, book_dune, --confirm]
```

The response is both data and navigation. An agent can follow `command` without reconstructing shell
syntax or assuming that every operation is valid in the current state.

## Why the frontier is bounded

An exhaustive action graph grows quickly with pagination, object collections, and high-branch-factor
trees. `next_actions` therefore contains only a small relevant frontier:

- an immediate continuation for a paginated result;
- a few state-valid actions for a returned object;
- a parameterized action plus a discovery source for many possible values.

When choices are omitted, collection metadata reports `total`, `returned`, and `truncated`, and a
concrete discovery action keeps them reachable. Completeness means discoverability, not expansion.

## Stable identity matters

Commands must carry durable reference values, not display labels or `str(object)`. A
`ReferenceCodec` separates `encode`, `decode`, and `display`, so a human-readable label can change
without breaking a saved action.

Continue with the [bookstore trajectory](../tutorials/bookstore.md) or the
[references and actions guide](../how-to/references-and-actions.md).

