# Documentation instructions

These instructions extend the repository-root `AGENTS.md` for `docs/`.

- Organize durable docs as tutorials, concepts, how-to guides, and references; plans record design
  history and are not the primary user journey.
- Link concepts to executable examples and precise contracts.
- Explain HATEOAS in plain language before relying on the acronym.
- Never claim shipped behavior without verifying it against code and tests.
- Keep internal Markdown links relative and resolvable.
- Keep CLI and MCP examples semantically aligned: CLI actions follow `command`; MCP actions follow
  `operation` plus `bound` arguments.
- Document MCP wire names such as `structuredContent` and `nextCursor` separately from Python SDK
  attributes such as `structured_content` and `next_cursor`.
- Keep `docs/README.md` as the durable navigation map. Plans preserve history; they are never a
  primary reader journey.
