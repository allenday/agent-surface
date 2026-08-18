# Core package instructions

These instructions extend the repository-root `AGENTS.md` for `src/agent_surface/`.

- Keep contracts transport-neutral and Pydantic-first.
- Preserve stable error codes, original argv boundaries, output budgets, and bounded
  `next_actions` semantics.
- Add public exports intentionally and test them; avoid import-time adapter side effects.
- A renderer may change presentation, never meaning. No silent truncation or ellipsis omission.
- Run focused unit tests plus `uv run mypy src` for changes here.

