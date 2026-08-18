# Test instructions

These instructions extend the repository-root `AGENTS.md` for `tests/`.

- Follow RED-GREEN-REFACTOR for behavior changes and retain the regression test.
- Prefer public APIs and real Pydantic models over implementation mocks.
- Assert semantics and stable error codes; snapshot formatting only when formatting is the contract.
- Keep reference-consumer fixtures domain-owned and free of transport imports.
- Repository metadata tests should verify that examples run and internal documentation links resolve.

