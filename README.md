# agent-surface

[![CI](https://github.com/allenday/agent-surface/actions/workflows/ci.yml/badge.svg)](https://github.com/allenday/agent-surface/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agent-surface.svg)](https://pypi.org/project/agent-surface/)
[![Python](https://img.shields.io/pypi/pyversions/agent-surface.svg)](https://pypi.org/project/agent-surface/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Define a typed Python operation once, then project it as a YAML-first CLI, MCP tools, and
machine-readable schemas.

> [!NOTE]
> The typed operation core and transport-neutral YAML/JSON renderer work today. CLI, discovery,
> MCP, and OpenAPI adapters are under active development; the public API may change before 1.0.

## Install

`agent-surface` requires Python 3.12 or newer.

```bash
pip install agent-surface
```

For development from source, use the locked environment:

```bash
git clone git@github.com:allenday/agent-surface.git
cd agent-surface
uv sync --frozen --all-extras --dev
make check
```

## Define an operation

```python
from agent_surface import App
from pydantic import BaseModel


class GreetRequest(BaseModel):
    name: str


class Greeting(BaseModel):
    message: str


app = App("hello")


@app.operation("greet", summary="Greet one person", read_only=True)
def greet(request: GreetRequest) -> Greeting:
    return Greeting(message=f"Hello, {request.name}!")
```

The operation registry validates inputs and outputs with Pydantic and accepts synchronous or
asynchronous handlers. Planned adapters consume the same registry instead of redefining
transport-specific contracts.

## Render bounded output

YAML with adaptive flow style is the default. Small leaf dictionaries and lists stay compact;
multiline text and larger structures remain block-oriented.

```python
from agent_surface import (
    Action,
    BoundedCollection,
    OutputBudget,
    RenderOptions,
    render,
)

page = BoundedCollection[str].from_sequence(
    ("resource-1", "resource-2", "resource-3"),
    budget=OutputBudget(max_items=2),
    continuation=Action(
        rel="next-page",
        command=("inventory", "resource", "list", "--cursor", "resource-2"),
    ),
)

print(render(page))
print(render(page, options=RenderOptions(yaml_style="flow")))
print(render(page, options=RenderOptions(format="json")))
```

`OutputBudget` defaults to 20 returned items and 65,536 UTF-8 bytes. It never silently slices a
raw collection. Truncation is valid only through `BoundedCollection`, which requires a concrete
continuation action. `render_envelope` converts an oversized success envelope into a complete
structured error envelope when that error fits the configured byte budget.

## Design principles

- YAML-first structured output, with compact flow style for small documents
- bounded results and `next_actions`, never silent truncation
- stable reference codecs instead of incidental object stringification
- opt-in introspection of Pydantic fields and decorated method signatures
- one typed source of truth across CLI, MCP, and schema adapters

See the [validated design](docs/plans/2026-08-18-agent-surface-design.md),
[adoption boundary](docs/adoption.md), [contribution guide](CONTRIBUTING.md), and
[release guide](docs/releasing.md).

## License

MIT
