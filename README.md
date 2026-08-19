# agent-surface

[![CI](https://github.com/allenday/agent-surface/actions/workflows/ci.yml/badge.svg)](https://github.com/allenday/agent-surface/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agent-surface.svg)](https://pypi.org/project/agent-surface/)
[![Python](https://img.shields.io/pypi/pyversions/agent-surface.svg)](https://pypi.org/project/agent-surface/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Define a typed Python operation once. Invoke it directly, project it as a YAML-first Click CLI or
native MCP server, and publish bounded instructions for what an agent can validly do next.

`agent-surface` is agent-first and developer-friendly: Pydantic remains the source of truth, output
is compact and inspectable, errors explain how to recover, and no adapter contains business logic.

> [!NOTE]
> Typed operations, adaptive YAML/JSON rendering, references, bounded actions, and generated Click
> CLIs and MCP v2 servers work today. The public API may change before 1.0.

## Five-minute bookstore

Clone the repository and create the locked Python 3.12+ environment:

```bash
git clone git@github.com:allenday/agent-surface.git
cd agent-surface
uv sync --frozen --all-extras --dev
./examples/bookstore books search --query dune --limit 2
```

The [complete bookstore source](examples/bookstore.py) is consumer-owned domain code wrapped by one
integration boundary. It includes an async search, stable book references, a generated Click CLI,
bounded actions, and confirmed mutations. Books are seeded domain data; holds use a small SQLite
store so create, read, cancel, and delete remain visible across CLI and MCP processes. Set
`AGENT_SURFACE_BOOKSTORE_DB` to choose the database path.

For use in your own project:

```bash
pip install agent-surface
pip install 'agent-surface[mcp]'
```

## A trajectory through application state

Suppose an agent knows only one entry command: search the bookstore. The response contains data and
the exact valid transitions from that state.

```bash
./examples/bookstore books search --query dune --limit 2
```

```yaml
schema_version: '1'
ok: true
command:
  raw:
  - ./examples/bookstore
  - books
  - search
  - --query
  - dune
  - --limit
  - '2'
  parsed:
    path: [books, search]
    args: {}
    options: {query: dune, limit: 2}
    flags: []
result:
  query: dune
  items:
  - ref: {value: book_dune}
    title: Dune
    author: Frank Herbert
  - ref: {value: book_dune_messiah}
    title: Dune Messiah
    author: Frank Herbert
  total: 3
  returned: 2
  truncated: true
  next_cursor: book_dune_messiah
next_actions:
  items:
  - rel: inspect
    description: Inspect the first returned book
    command: [./examples/bookstore, books, inspect, --book, book_dune]
    operation: books.inspect
    bound: {book: book_dune}
    slots: {}
  - rel: next-page
    description: Continue this search
    command:
    - ./examples/bookstore
    - books
    - search
    - --query
    - dune
    - --cursor
    - book_dune_messiah
    - --limit
    - '2'
    operation: books.search
    bound: {query: dune, cursor: book_dune_messiah, limit: 2}
    slots: {}
  total: 2
  returned: 2
  truncated: false
```

The agent chooses the returned `inspect` command without guessing a route or reconstructing a shell
string:

```bash
./examples/bookstore books inspect --book book_dune
```

```yaml
schema_version: '1'
ok: true
command:
  raw: [./examples/bookstore, books, inspect, --book, book_dune]
  parsed:
    path: [books, inspect]
    args: {}
    options: {book: book_dune}
    flags: []
result:
  ref: {value: book_dune}
  title: Dune
  author: Frank Herbert
  available: true
next_actions:
  items:
  - rel: reserve
    description: Reserve this available book
    command: [./examples/bookstore, holds, create, --book, book_dune, --confirm]
    operation: holds.create
    bound: {book: book_dune, confirm: true}
    slots: {}
  total: 1
  returned: 1
  truncated: false
```

The next response advertises a confirmed write. The adapter enforces `--confirm` before calling the
handler:

```bash
./examples/bookstore holds create --book book_dune --confirm
```

```yaml
schema_version: '1'
ok: true
command:
  raw: [./examples/bookstore, holds, create, --book, book_dune, --confirm]
  parsed:
    path: [holds, create]
    args: {}
    options: {book: book_dune}
    flags: [confirm]
result:
  id: hold_book_dune
  book: {value: book_dune}
  status: active
next_actions:
  items:
  - rel: get
    description: Read this hold
    command: [./examples/bookstore, holds, get, --hold, hold_book_dune]
    operation: holds.get
    bound: {hold: hold_book_dune}
    slots: {}
  - rel: cancel
    description: Cancel this hold
    command: [./examples/bookstore, holds, cancel, --hold, hold_book_dune, --confirm]
    operation: holds.cancel
    bound: {hold: hold_book_dune, confirm: true}
    slots: {}
  - rel: delete
    description: Delete this hold
    command: [./examples/bookstore, holds, delete, --hold, hold_book_dune, --confirm]
    operation: holds.delete
    bound: {hold: hold_book_dune, confirm: true}
    slots: {}
  total: 3
  returned: 3
  truncated: false
```

The hold can now be read with `holds.get`, transitioned to `cancelled` with `holds.cancel`, or
physically removed with `holds.delete`. The same SQLite state is available to MCP clients through
the [`examples/bookstore-mcp`](examples/bookstore-mcp) stdio server. The
[bookstore integration guide](docs/tutorials/bookstore.md#connect-codex-and-claude-code) shows the
Codex and Claude Code configuration.

That is HATEOAS—Hypermedia as the Engine of Application State—in practical terms: the response tells
the caller what it can validly do next. An agent follows those exact links and command arrays through
application state instead of memorizing an undocumented command tree. Read the
[plain-language HATEOAS explanation](docs/concepts/hateoas.md) or continue the
[complete bookstore tutorial](docs/tutorials/bookstore.md).

## Define and project an operation

The domain model stays independent of Click:

```python
from pydantic import BaseModel
from agent_surface import App
from agent_surface.adapters.click import build_click_group


class GreetRequest(BaseModel):
    name: str


class Greeting(BaseModel):
    message: str


app = App("hello")


@app.operation("people.greet", summary="Greet one person", read_only=True)
def greet(request: GreetRequest) -> Greeting:
    return Greeting(message=f"Hello, {request.name}!")


cli = build_click_group(app)
```

Invoke `app.invoke(...)` from Python or mount `cli` beneath an existing Click group. Both paths use
the same request model, handler, result model, and stable `OperationError` semantics. See the
[Python API guide](docs/reference/python-api.md), [CLI contract](docs/reference/cli-contract.md), or
[existing-application adoption guide](docs/how-to/adopt-an-existing-app.md).

## Project the same registry through MCP

MCP is a sibling adapter, not a wrapper around Click:

```python
from agent_surface.adapters.mcp import MCPAdapter

mcp = MCPAdapter(app)
```

`mcp.server` is the native low-level MCP server for embedding and tests. Run it over stdio with
`await mcp.run_stdio()`, or obtain its ASGI application with `mcp.streamable_http_app()`. Tools keep
their exact dotted operation names, Pydantic schemas, safety annotations, structured outcomes, and
bounded discovery cursors. Pass the same `references=` and `action_provider=` integrations used by
Click when your operations use stable object references or advertise next actions.

In MCP responses, an advertised action's `operation` and `bound` fields are the next tool name and
arguments. The complete search → inspect → reserve journey is executable in the
[bookstore tutorial](docs/tutorials/bookstore.md); protocol details are in the
[MCP contract](docs/reference/mcp-contract.md).

## Bounded output by construction

YAML with adaptive flow style is the default. Small leaf collections stay on one line; larger and
multiline structures remain block-oriented. JSON and explicit styles are presentation choices:

```python
from agent_surface import BoundedCollection, RenderOptions, render, render_envelope

print(render(value))
print(render(value, options=RenderOptions(yaml_style="flow")))
print(render(value, options=RenderOptions(format="json")))
```

The default `OutputBudget` permits 20 returned items and 65,536 UTF-8 bytes. `BoundedCollection`
requires a concrete continuation whenever it truncates. `render_envelope` converts an oversized
success document into a complete structured error when possible. Nothing silently disappears, and
ellipsis is never an omission protocol.

## References and action discovery

Stable identity is separate from display text. A `ReferenceCodec` implements `encode`, `decode`, and
`display`; `ReferenceRegistry` performs exact-type lookup and never falls back to `str(object)`.

Action candidates come only from registered operations or explicitly `@action`-decorated methods.
`AllowActions` or another explicit policy authorizes publication. `ActionCatalog` returns bounded,
cursor-addressable pages with one immediate continuation instead of serializing the reachable graph.
See [references and actions](docs/how-to/references-and-actions.md).

## Choose your path

- Learn by doing: [bookstore tutorial](docs/tutorials/bookstore.md)
- Understand the model: [HATEOAS and bounded discovery](docs/concepts/hateoas.md)
- Adopt incrementally: [existing application guide](docs/how-to/adopt-an-existing-app.md) and the
  original [adoption boundary](docs/adoption.md)
- Integrate precisely: [Python API](docs/reference/python-api.md) and
  [CLI envelope, discovery, and exits](docs/reference/cli-contract.md), or the
  [MCP contract](docs/reference/mcp-contract.md)
- Contribute or release: [CONTRIBUTING.md](CONTRIBUTING.md) and
  [release guide](docs/releasing.md)

## Design principles

- one typed operation registry; sibling transport adapters
- YAML-first structured output with compact flow style for small values
- HATEOAS responses with a bounded relevant `next_actions` frontier
- stable references instead of incidental stringification
- explicit policy and confirmation gates for actions and writes
- original argv boundaries, repair-oriented errors, and deterministic discovery
- excellent developer experience without weakening agent contracts

## License

MIT
