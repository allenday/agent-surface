# Workflow instructions

These instructions extend `.github/AGENTS.md` for `.github/workflows/`.

- Keep each workflow's trigger, permissions, artifact boundary, and failure behavior obvious near its definition.
- Prefer the repository's `make check` gate for CI parity; pin every action to an immutable SHA.
- Release workflows must build once, publish the same artifacts, and use OIDC environments without secrets.
- Validate workflow YAML and repository metadata tests after changes.
