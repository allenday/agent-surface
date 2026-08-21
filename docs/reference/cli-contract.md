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

## Sensitive stdin fields

A sensitive singular string field may opt into one bounded stdin value for the Click projection:

```python
bws_token: str = Field(
    min_length=1,
    json_schema_extra={
        "sensitive": True,
        "cli": {
            "source": "stdin",
            "max_bytes": 8192,
            "strip_trailing_newline": True,
        },
    },
)
```

The generated CLI omits `--bws-token`; it requires the explicit presence flag
`--bws-token-stdin` instead:

```bash
printf '%s\n' "$BWS_TOKEN" | app host bootstrap HOST --bws-token-stdin
```

The adapter accepts at most `max_bytes` input bytes in one bounded read. It accepts one UTF-8 value with at most one
trailing newline; `stdin_missing`, `stdin_empty`, `stdin_multiple_values`, `stdin_too_large`, and
`stdin_invalid_encoding` are structured exit-code-2 errors. The value never appears in argv,
command envelopes, generated actions, or rendered errors. Only one stdin-sourced field is allowed
per operation.

This is a Click-only input source. MCP continues to expose `bws_token` as the ordinary typed
request field, and its normal sensitive-value redaction applies.

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
The Click adapter requires `max_bytes >= 1024`, the minimum reserved for its structured emergency
error envelope. Smaller budgets fail adapter construction with `cli_budget_too_small` rather than
being silently exceeded at runtime.

## Discovery

Use `operations list`, `operations describe OPERATION`, `actions list`, and `actions explain` for
machine-readable discovery. Listings are cursor-paginated. Human-oriented Click `--help` remains
available.

See the [bookstore tutorial](../tutorials/bookstore.md) for an executable interaction.
