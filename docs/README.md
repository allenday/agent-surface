# Documentation map

Start with the path that matches your goal. Each path leads to durable documentation; plans record
how past decisions were made, not how to use the library today.

## Evaluate

Read [HATEOAS and bounded discovery](concepts/hateoas.md), then run the
[bookstore tutorial](tutorials/bookstore.md). It is the fastest way to see a real response advertise
its next valid action.

## Adopt

Read [adopting an existing application](how-to/adopt-an-existing-app.md) for the integration
boundary, then the [Python API reference](reference/python-api.md) for the public types. Add
[references and actions](how-to/references-and-actions.md) when your domain needs stable object
identity or scoped action discovery.

## Connect

Use the [bookstore MCP integration](tutorials/bookstore.md#connect-codex-and-claude-code) for a
local working client, then consult the [MCP contract](reference/mcp-contract.md) or
[CLI contract](reference/cli-contract.md) for transport details.

## Contribute

Read [CONTRIBUTING.md](../CONTRIBUTING.md), follow the repository's `AGENTS.md`, and finish with
`make check`. The [release guide](releasing.md) covers trusted publishing.

## Documentation types

- **Tutorials** teach an end-to-end workflow.
- **Concepts** explain an invariant and why it exists.
- **How-to guides** solve one production task.
- **References** specify shipped behavior precisely.
- **Plans** preserve approved design and implementation history; they are not canonical docs.
