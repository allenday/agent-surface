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

The example stores holds in SQLite. Python 3.12's `sqlite3` standard library module provides the
driver, so there is no additional pip or uv dependency. (A custom Python build that omits SQLite is
not supported.) By default the CLI uses `$XDG_DATA_HOME/agent-surface/bookstore.sqlite3`, falling
back to `~/.local/share/agent-surface/bookstore.sqlite3`. Set an explicit path when you want CLI and
MCP processes to share a known store:

```bash
export AGENT_SURFACE_BOOKSTORE_DB="$HOME/.local/share/agent-surface/bookstore.sqlite3"
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

The resulting hold advertises the complete toy CRUD lifecycle:

```bash
./examples/bookstore holds get --hold hold_book_dune
./examples/bookstore holds cancel --hold hold_book_dune --confirm
./examples/bookstore holds delete --hold hold_book_dune --confirm
```

Cancellation is an update: the row remains readable with `status: cancelled`. Deletion physically
removes it. The caller never needs to invent a route, stringify a Python object, or load the entire
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

## Connect Codex and Claude Code

The repository includes [`examples/bookstore-mcp`](../../examples/bookstore-mcp), an executable
stdio entry point that uses the repository's `.venv`. Use absolute paths in client configuration so
the server does not depend on the client's working directory. First run `uv sync --all-extras
--dev`, then register it with Codex:

```bash
codex mcp add bookstore --env AGENT_SURFACE_BOOKSTORE_DB=/absolute/path/to/bookstore.sqlite3 -- /absolute/path/to/agent-surface/examples/bookstore-mcp
codex mcp list
```

The equivalent entry in `~/.codex/config.toml` is:

```toml
[mcp_servers.bookstore]
command = "/absolute/path/to/agent-surface/examples/bookstore-mcp"

[mcp_servers.bookstore.env]
AGENT_SURFACE_BOOKSTORE_DB = "/absolute/path/to/bookstore.sqlite3"
```

Restart Codex after changing its configuration, then use `/mcp` to inspect the connection. See the
[official Codex MCP configuration](https://developers.openai.com/codex/mcp) for project-local
configuration, timeouts, and approval settings.

For a user-scoped Claude Code server:

```bash
claude mcp add --transport stdio --scope user --env AGENT_SURFACE_BOOKSTORE_DB=/absolute/path/to/bookstore.sqlite3 bookstore -- /absolute/path/to/agent-surface/examples/bookstore-mcp
claude mcp list
```

Or commit this portable project-scoped `.mcp.json`. Claude expands `CLAUDE_PROJECT_DIR`, and the
server uses the default user-data database because this form intentionally omits the environment
override:

```json
{
  "mcpServers": {
    "bookstore": {
      "command": "${CLAUDE_PROJECT_DIR:-.}/examples/bookstore-mcp"
    }
  }
}
```

Use `/mcp` in Claude Code to inspect or authenticate configured servers. See the
[official Claude Code MCP guide](https://code.claude.com/docs/en/mcp) for scope and transport
details. Both clients invoke the same dotted tools and persist holds in the same database when they
share `AGENT_SURFACE_BOOKSTORE_DB`.

The checked-in `examples/bookstore-mcp` convenience wrapper targets POSIX shells on macOS and Linux.
On Windows, configure the client to run the checkout's `.venv\Scripts\python.exe` with arguments
`-m examples.bookstore_mcp` and the repository root as its working directory. SQLite itself remains
cross-platform and still requires no separate package.
