# Adapter instructions

These instructions extend the repository-root and package `AGENTS.md` files.

- Click and MCP are sibling projections of the operation registry.
- Do not put business rules in adapters or invoke one transport through another.
- Preserve structured success and repairable error envelopes on every handled path.
- Keep discovery machine-readable and paginated; normal transport-native help remains available.
- Redact sensitive argv and parsed values, and enforce confirmation before handler invocation.

