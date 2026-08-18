# CLI contract

`ClickAdapter` projects the operation registry as nested Click commands. YAML is the default;
`--format json` and `--yaml-style auto|flow|block` change presentation without changing semantics.

## Envelope

Every handled success or failure is structured:

```yaml
schema_version: '1'
ok: true
command:
  raw: [app, group, command, --option, value]
  parsed:
    path: [group, command]
    args: {}
    options: {option: value}
    flags: []
result: {}
next_actions: {items: [], total: 0, returned: 0, truncated: false}
```

`command.raw` preserves argv boundaries. Sensitive values are replaced with `<redacted>`. The
parsed view stays shallow and close to parser truth. For a generated group mounted beneath a
consumer-owned Click root, supply `argv_provider` to preserve parent options that Click consumed
before dispatching into the group.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | success |
| `2` | parse or validation error |
| `3` | confirmation required or policy denial |
| `4` | domain operation error |
| `70` | unexpected internal failure |

Errors include a stable code, message, repair guidance when available, and bounded next actions.
Oversized successes become complete structured size errors; output is never silently truncated.

## Discovery

Use `operations list`, `operations describe OPERATION`, `actions list`, and `actions explain` for
machine-readable discovery. Listings are cursor-paginated. Human-oriented Click `--help` remains
available.

See the [bookstore tutorial](../tutorials/bookstore.md) for an executable interaction.
