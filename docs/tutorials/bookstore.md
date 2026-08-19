# Bookstore tutorial

This tutorial follows one complete HATEOAS trajectory through the executable example in
[`examples/bookstore.py`](../../examples/bookstore.py). Start with only a search command; each
response supplies the valid next command.

## Run the example

From the repository root:

```bash
uv sync --frozen --all-extras --dev
./examples/bookstore books search --query dune --limit 2
```

The YAML response contains the matching books and a bounded `next_actions` collection. Follow the
returned `inspect` command verbatim:

```bash
./examples/bookstore books inspect --book book_dune
```

The detail response advertises `reserve` only when the book is available. That mutation is explicit
and confirmation-gated:

```bash
./examples/bookstore holds create --book book_dune --confirm
```

The resulting hold advertises the next valid transitions, such as inspecting its book or cancelling
the hold. The caller never needs to invent a route, stringify a Python object, or load the entire
application graph.

## Read the integration boundary

The example deliberately keeps four concerns visible:

- Pydantic request and result models describe domain data.
- `App` registers typed operations without Click imports in handlers.
- `BookRefCodec` gives object references stable wire identity.
- `BookstoreActions` chooses a small, relevant frontier for each result.

Read [`examples/bookstore.py`](../../examples/bookstore.py) from `build_surface()` outward, then see
[adopting an existing application](../how-to/adopt-an-existing-app.md) for the production pattern.

## Explore instead of guessing

The generated CLI includes machine-readable discovery:

```bash
./examples/bookstore operations list
./examples/bookstore operations describe books.search
./examples/bookstore actions list --operation books.inspect
```

Normal `--help` remains useful to humans. Discovery commands provide schemas, pagination, and stable
structured envelopes to agents. See the [CLI contract](../reference/cli-contract.md) for the exact
rules.

## Follow the same trajectory through MCP

Install the optional transport dependency with `pip install 'agent-surface[mcp]'`. The example's
`surface.mcp()` method projects the same registry, reference codec, and action provider as the CLI:

```python
import asyncio

from mcp import Client

from examples.bookstore import build_surface


async def main() -> None:
    surface = build_surface()
    async with Client(surface.mcp().server, raise_exceptions=True) as client:
        searched = await client.call_tool("books.search", {"query": "dune", "limit": 2})
        inspect = next(
            item
            for item in searched.structured_content["next_actions"]["items"]
            if item["rel"] == "inspect"
        )
        inspected = await client.call_tool(inspect["operation"], inspect["bound"])
        reserve = next(
            item
            for item in inspected.structured_content["next_actions"]["items"]
            if item["rel"] == "reserve"
        )
        held = await client.call_tool(reserve["operation"], reserve["bound"])
        assert held.structured_content["result"]["status"] == "active"


asyncio.run(main())
```

The CLI follows each action's `command`; MCP follows the same action's `operation` and `bound`
arguments. `bound` includes `confirm: true` for the advertised reservation, while the MCP adapter
still independently enforces confirmation before invoking the handler. The in-memory client above
is useful for integration tests. Production processes can call `await surface.mcp().run_stdio()` or
mount `surface.mcp().streamable_http_app()`.

See the [MCP contract](../reference/mcp-contract.md) for schemas, errors, discovery, and transports.
