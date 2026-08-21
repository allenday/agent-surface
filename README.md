# agent-surface

[![CI](https://github.com/allenday/agent-surface/actions/workflows/ci.yml/badge.svg)](https://github.com/allenday/agent-surface/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agent-surface.svg)](https://pypi.org/project/agent-surface/)
[![Python](https://img.shields.io/pypi/pyversions/agent-surface.svg)](https://pypi.org/project/agent-surface/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Typed Python operations that become [HATEOAS](https://en.wikipedia.org/wiki/HATEOAS)
CLI and [MCP](https://modelcontextprotocol.io/docs/getting-started/intro) surfaces—so people and
agents can discover and take the next valid action without guessing commands, routes, or object
encodings.

Define an operation once with Pydantic; project it as a YAML-first Click CLI and native MCP tools
with bounded, concrete `next_actions`.

## In 30 seconds

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

Install it and run the command:

```bash
pip install 'agent-surface[mcp]'
python hello.py people greet --name Ada
```

The same typed operation is now callable from Python, exposed through Click, and available as the
exact MCP tool `people.greet`.

## Use it from MCP

For a local client, use **stdio**: the client starts `hello.py --mcp` and exchanges MCP messages
over its standard input and output.

Add this to `~/.codex/config.toml`, replacing both absolute paths with yours. `python` must be the
interpreter where you installed `agent-surface`:

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

Streamable HTTP is for serving MCP remotely from a web application; it is not needed for this
local setup. See the [MCP contract](docs/reference/mcp-contract.md) when you need that deployment.

## Why HATEOAS matters here

HATEOAS—Hypermedia as the Engine of Application State—means a response advertises the concrete
transitions valid from its current state. A caller follows them; it does not reconstruct a command
tree from memory.

For example, in the [bookstore tutorial](docs/tutorials/bookstore.md) tutorial, a call like:

```bash
./examples/bookstore books search --query dune --limit 2
```

produces output like:

```yaml
result:
  items: [{ref: {value: book_dune}, title: Dune}]
next_actions:
  items:
  - rel: inspect
    command: [./examples/bookstore, books, inspect, --book, book_dune]
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

## Author a surface with the skill

Use the portable `agent-friendly-cli-design` skill to design an agent-first CLI in any stack:

```bash
mkdir -p ~/.codex/skills/agent-friendly-cli-design
curl -fsSL https://raw.githubusercontent.com/allenday/agent-surface/main/src/agent_surface/skills/agent-friendly-cli-design/SKILL.md \
  -o ~/.codex/skills/agent-friendly-cli-design/SKILL.md
curl -fsSL https://raw.githubusercontent.com/allenday/agent-surface/main/src/agent_surface/skills/agent-friendly-cli-design/reference.md \
  -o ~/.codex/skills/agent-friendly-cli-design/reference.md
```

On the next Codex turn, ask it to use `agent-friendly-cli-design` to author a new surface. Read the
[SKILL.md](src/agent_surface/skills/agent-friendly-cli-design/SKILL.md) directly for the durable
command, envelope, discovery, output-budget, and next-action contracts it teaches.

When building with this package, also install the companion recipe:

```bash
mkdir -p ~/.codex/skills/agent-surface-authoring
curl -fsSL https://raw.githubusercontent.com/allenday/agent-surface/main/src/agent_surface/skills/agent-surface-authoring/SKILL.md \
  -o ~/.codex/skills/agent-surface-authoring/SKILL.md
curl -fsSL https://raw.githubusercontent.com/allenday/agent-surface/main/src/agent_surface/skills/agent-surface-authoring/reference.md \
  -o ~/.codex/skills/agent-surface-authoring/reference.md
```

On the next turn, ask Codex to use `agent-surface-authoring`; it applies the shared principles to
Pydantic, `App`, Click, MCP, references, actions, and package verification. Its
[SKILL.md](src/agent_surface/skills/agent-surface-authoring/SKILL.md) is shipped with the package.

## Principles

- one typed operation registry; sibling Python, Click, and MCP adapters
- YAML-first structured output with compact flow style for small values
- bounded HATEOAS `next_actions`, stable references, and explicit confirmation for writes
- predictable discovery and repair-oriented errors

For contribution and release details, see [CONTRIBUTING.md](CONTRIBUTING.md) and the
[release guide](docs/releasing.md).

## License

MIT
