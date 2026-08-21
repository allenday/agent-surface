# agent-surface

[![CI](https://github.com/allenday/agent-surface/actions/workflows/ci.yml/badge.svg)](https://github.com/allenday/agent-surface/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agent-surface.svg)](https://pypi.org/project/agent-surface/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Typed Python operations that become [HATEOAS](https://en.wikipedia.org/wiki/HATEOAS) CLI and
[MCP](https://modelcontextprotocol.io/docs/getting-started/intro) surfaces. A response tells a
person or agent the next valid thing to do, so callers follow concrete actions instead of guessing
commands, routes, or object encodings.

Define an operation once with Pydantic. `agent-surface` projects it as a YAML-first Click CLI and
native MCP tools with bounded, concrete `next_actions`.

## See a HATEOAS trajectory

From a checkout of this repository, run the bookstore example:

```bash
uv sync --frozen --all-extras --dev
./examples/bookstore books search --query dune --limit 2
```

The relevant fields from its YAML envelope show the first page and its concrete next actions:

```yaml
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
    command: [./examples/bookstore, books, search, --query, dune, --cursor, book_dune_messiah, --limit, '2']
    operation: books.search
    bound: {query: dune, cursor: book_dune_messiah, limit: 2}
    slots: {}
  total: 2
  returned: 2
  truncated: false
```

Follow the advertised CLI command verbatim:

```bash
./examples/bookstore books inspect --book book_dune
```

For MCP, call `operation: books.inspect` with `bound: {book: book_dune}` instead. The complete
search → inspect → reserve → cancel → delete trajectory is executable in the
[bookstore tutorial](docs/tutorials/bookstore.md).

## Use the library now

Save this as `hello.py`:

```python
import asyncio
import sys

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
    if sys.argv[1:] == ["--mcp"]:
        asyncio.run(mcp.run_stdio())
    else:
        cli()
```

Install the package into your existing Python environment and run the CLI:

```bash
pip install 'agent-surface[mcp]'
python hello.py people greet --name Ada
```

The same typed operation is callable from Python, exposed through Click, and available as the exact
MCP tool `people.greet`.

## Connect it to MCP

For a local client, use **stdio**: the client starts `hello.py --mcp` and exchanges MCP messages
over standard input and output. Add this to `~/.codex/config.toml`, replacing both absolute paths.
`python` must be the interpreter where you installed `agent-surface`:

```toml
[mcp_servers.hello]
command = "/absolute/path/to/.venv/bin/python"
args = ["/absolute/path/to/hello.py", "--mcp"]
```

Restart Codex, then use `/mcp` to inspect `hello`. For Claude Code, save the equivalent
project-local `.mcp.json` next to `hello.py`:

```json
{
  "mcpServers": {
    "hello": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["/absolute/path/to/hello.py", "--mcp"]
    }
  }
}
```

Streamable HTTP is only for serving MCP remotely from a web application. See the
[MCP contract](docs/reference/mcp-contract.md) when you need that deployment.

## Author a new surface

Install the optional authoring skills for an agent that will build a HATEOAS CLI or MCP tool:

```bash
curl -fsSL https://raw.githubusercontent.com/allenday/agent-surface/main/src/agent_surface/skills/install.sh | sh
```

The `agent-surface-authoring` skill first checks how the current project manages Python before it
uses the library; it does not choose a virtual environment or install packages globally. You can
also read the skills directly:

- [agent-surface-authoring/SKILL.md](src/agent_surface/skills/agent-surface-authoring/SKILL.md)
- [agent-friendly-cli-design/SKILL.md](src/agent_surface/skills/agent-friendly-cli-design/SKILL.md)

## Go deeper when needed

Start with the [documentation map](docs/README.md) if you are unsure which path fits.

- **Evaluate the approach.** Read [HATEOAS and bounded discovery](docs/concepts/hateoas.md), then
  run the [bookstore example](examples/bookstore.py).
- **Adopt it in an application.** Start with the [Python API](docs/reference/python-api.md) and
  [existing-application guide](docs/how-to/adopt-an-existing-app.md), then add
  [references and actions](docs/how-to/references-and-actions.md).
- **Connect an agent.** Follow the [bookstore MCP integration](docs/tutorials/bookstore.md#connect-codex-and-claude-code),
  [MCP contract](docs/reference/mcp-contract.md), and [CLI contract](docs/reference/cli-contract.md).
- **Contribute or release.** Read [CONTRIBUTING.md](CONTRIBUTING.md) and the
  [release guide](docs/releasing.md).

## Principles

- one typed operation registry; sibling Python, Click, and MCP adapters
- YAML-first structured output with compact flow style for small values
- bounded HATEOAS `next_actions`, stable references, and explicit confirmation for writes
- predictable discovery and repair-oriented errors

## License

MIT
