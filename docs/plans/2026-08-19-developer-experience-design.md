# Agent-First Developer Experience Design

## Purpose and standard

Make the value of `agent-surface` obvious to a developer in minutes while retaining agent-first
contracts. Agent-first is an architectural constraint, not permission for a poor human experience.

The documentation succeeds when a new developer can:

1. understand the promise in 30 seconds;
2. install and run a working example in five minutes;
3. watch an agent traverse application state through returned actions;
4. understand why HATEOAS, budgets, references, and policy gates exist; and
5. find the correct extension point without reading package internals.

## Documentation architecture

```text
README.md
├── five-minute bookstore quickstart
├── complete HATEOAS trajectory
├── what just happened?
└── choose your path
    ├── docs/tutorials/bookstore.md
    ├── docs/concepts/hateoas.md
    ├── docs/how-to/adopt-an-existing-app.md
    ├── docs/how-to/references-and-actions.md
    ├── docs/reference/cli-contract.md
    ├── docs/reference/mcp-contract.md
    └── docs/reference/python-api.md
```

The README leads with behavior rather than component inventory. It includes copy-and-paste setup, a
small complete application, real commands, complete compact YAML responses, and explicit links to
deeper material. Claims distinguish shipped behavior from planned behavior.

## The bookstore trajectory

The canonical example is a bookstore because it naturally demonstrates search pagination, stable
references, branching actions, read-only inspection, and a confirmed write.

```text
operations list
    |
books search --query dune --limit 2
    | choose the returned inspect action
books inspect --book book_dune
    | choose the returned reserve action
holds create --book book_dune --confirm
    | choose show or cancel
```

The README explains HATEOAS in plain language before using the acronym:

> The response tells the caller what it can validly do next. An agent follows those links and exact
> command arrays through application state instead of memorizing an undocumented command tree.

Every displayed response is complete. Small structures use flow YAML; pagination and omission are
explicit; examples never use `...`. Each next command is copied verbatim from the preceding
`next_actions` value.

`examples/bookstore.py` is runnable and consumer-owned: its domain models and service do not import
Click or MCP. It exposes direct invocation, the generated CLI, and—after the MCP adapter lands—the
same registry as MCP tools.

## Information types

- Tutorial: a guided bookstore journey with expected results.
- Concepts: HATEOAS, bounded progressive disclosure, stable references, and transport siblings.
- How-to guides: adopt an existing app, add codecs/actions, mount Click, and serve MCP.
- Reference: public Python API, CLI envelope/exit codes, and MCP schemas/error semantics.

Documents link laterally when a concept becomes operational. The tutorial links to explanations and
reference; reference pages link back to working examples. `docs/adoption.md` becomes the existing-app
how-to rather than a disconnected architecture note.

## Scoped agent instructions

Root `AGENTS.md` states the project-wide HATEOAS and DX invariants. Scoped files add only local
knowledge:

- `src/agent_surface/AGENTS.md`: public contracts and dependency direction
- `src/agent_surface/adapters/AGENTS.md`: thin sibling adapters and safety/error parity
- `src/agent_surface/skills/AGENTS.md`: bundled skill and sidecar synchronization
- `tests/AGENTS.md`: contract equivalence and required RED/GREEN evidence
- `examples/AGENTS.md`: executable, consumer-owned, documentation-tested examples
- `docs/AGENTS.md`: truthful claims, complete outputs, and link structure
- `.github/AGENTS.md`: pinned actions, least privilege, and trusted publishing

Instructions inherit recursively and should not repeat their parents.

## Verification

The bookstore example runs in tests through direct invocation and each shipped adapter. Repository
metadata tests require the HATEOAS explanation, the multi-step trajectory, critical internal links,
and scoped `AGENTS.md` files. Tests validate internal Markdown links and forbid documentation from
claiming unshipped adapters.

CLI output fixtures used in documentation come from the same behavior exercised by tests. `make
check` remains the single completion gate for code, documentation contracts, type checking, and
distribution contents.
