# agent-surface

[![CI](https://github.com/allenday/agent-surface/actions/workflows/ci.yml/badge.svg)](https://github.com/allenday/agent-surface/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agent-surface.svg)](https://pypi.org/project/agent-surface/)
[![Python](https://img.shields.io/pypi/pyversions/agent-surface.svg)](https://pypi.org/project/agent-surface/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Typed Python operations that become [HATEOAS](https://ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm#sec_5_2_3)
CLI and [MCP](https://modelcontextprotocol.io/docs/getting-started/intro) surfaces—so people and
agents can discover and take the next valid action without guessing commands, routes, or object
encodings.

Define an operation once with Pydantic; project it as a YAML-first Click CLI and native MCP tools
with bounded, concrete `next_actions`.

## In 30 seconds

Install the package, then save this as `hello.py`:

```bash
pip install 'agent-surface[mcp]'
```

```python
from pydantic import BaseModel

from agent_surface import App
from agent_surface.adapters.click import build_click_group
from agent_surface.adapters.mcp import MCPAdapter


class GreetRequest(BaseModel):
    name: str


class Greeting(BaseModel):
    message: str


app = App("hello")


@app.operation("people.greet", summary="Greet one person", read_only=True)
def greet(request: GreetRequest) -> Greeting:
    return Greeting(message=f"Hello, {request.name}!")


cli = build_click_group(app)
mcp = MCPAdapter(app)

if __name__ == "__main__":
    cli()
```

```bash
python hello.py people greet --name Ada
```

The same typed operation is now callable from Python, exposed through Click, and available as the
exact MCP tool `people.greet`. Mount `cli` in an existing Click application, run `mcp` over stdio,
or obtain its Streamable HTTP ASGI application.

## Why HATEOAS matters here

HATEOAS—Hypermedia as the Engine of Application State—means a response advertises the concrete
transitions valid from its current state. A caller follows them; it does not reconstruct a command
tree from memory.

```yaml
result:
  items: [{ref: {value: book_dune}, title: Dune}]
next_actions:
  items:
  - rel: inspect
    command: [bookstore, books, inspect, --book, book_dune]
    operation: books.inspect
    bound: {book: book_dune}
  total: 1
  returned: 1
  truncated: false
```

For Click, follow `command`. For MCP, call `operation` with `bound`. The complete executable
search → inspect → reserve → cancel → delete trajectory is in the
[bookstore tutorial](docs/tutorials/bookstore.md).

## Choose your path

- **Evaluate the idea.** Read [HATEOAS and bounded discovery](docs/concepts/hateoas.md), then run
  the [bookstore example](examples/bookstore.py).
- **Adopt it in an application.** Start with the [Python API](docs/reference/python-api.md) and the
  [existing-application guide](docs/how-to/adopt-an-existing-app.md), then add
  [references and actions](docs/how-to/references-and-actions.md) when your domain needs them.
- **Connect an agent.** Follow the [bookstore MCP integration](docs/tutorials/bookstore.md#connect-codex-and-claude-code),
  [MCP contract](docs/reference/mcp-contract.md), and [CLI contract](docs/reference/cli-contract.md).

## For coding agents

Give an agent the shipped [agent-friendly CLI design instructions](src/agent_surface/skills/agent-friendly-cli-design/SKILL.md).
They define the durable command, envelope, discovery, output-budget, and next-action contracts the
package is designed to uphold.

## Principles

- one typed operation registry; sibling Python, Click, and MCP adapters
- YAML-first structured output with compact flow style for small values
- bounded HATEOAS `next_actions`, stable references, and explicit confirmation for writes
- predictable discovery and repair-oriented errors

For contribution and release details, see [CONTRIBUTING.md](CONTRIBUTING.md) and the
[release guide](docs/releasing.md).

## License

MIT
