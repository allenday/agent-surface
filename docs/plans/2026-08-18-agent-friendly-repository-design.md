# Agent-Friendly Repository Design

## Goal

Make `agent-surface` easy for coding agents, maintainers, and outside contributors to
understand, change, verify, and release without duplicating guidance or exposing long-lived
package-index credentials.

## Documentation surface

- Keep `README.md` human-first: purpose, status, installation, a minimal typed-operation
  example, project direction, badges, and links to deeper contributor material.
- Put executable repository instructions in one root `AGENTS.md`: architecture, exact setup
  and verification commands, package conventions, testing expectations, and completion checks.
- Keep public contribution and vulnerability-reporting processes in concise
  `CONTRIBUTING.md` and `SECURITY.md` files.
- Add small GitHub issue and pull-request templates. Avoid nested `AGENTS.md` files until a
  subtree needs genuinely different instructions.

## Automation

- CI runs tests on Python 3.12, 3.13, and 3.14. A dedicated quality job runs Ruff, mypy,
  distribution builds, and package-content checks.
- A separate release workflow builds distributions once, publishes manual runs to TestPyPI,
  and publishes GitHub Releases to PyPI.
- Both indexes use PyPI Trusted Publishing with dedicated `testpypi` and `pypi` GitHub
  environments. Only publishing jobs receive `id-token: write`; production should require
  manual approval.
- Pin actions to immutable commit SHAs and let Dependabot propose action and Python dependency
  updates.

## Project conventions

- Python support begins at 3.12; Ruff and mypy use that same baseline.
- The Pydantic operation contract remains the source of truth across adapters.
- YAML is the default machine-readable representation, with bounded progressive disclosure
  and no semantic ellipsis placeholders.
- Bundled skill sidecars are package data and must be verified in built wheels.
- Behavior changes are test-driven; all relevant checks must pass before completion.

## Release flow

1. CI verifies the commit and built distributions.
2. A maintainer manually dispatches `release.yml` to exercise TestPyPI.
3. A published GitHub Release triggers publication of the same version to PyPI.
4. GitHub exchanges OIDC identity for short-lived index credentials; no PyPI API tokens are
   stored in repository secrets.

The repository documents the exact owner, repository, workflow, and environment values needed
to register pending trusted publishers on TestPyPI and PyPI.
