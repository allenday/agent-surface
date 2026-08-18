# GitHub automation instructions

These instructions extend the repository-root `AGENTS.md` for `.github/`.

- Pin actions to immutable commit SHAs and retain least-privilege permissions.
- Keep CI aligned with the supported Python versions and the local `make check` gate.
- Releases use GitHub OIDC Trusted Publishing for TestPyPI and PyPI; never store API tokens here.
- Keep issue and pull-request templates concise, structured, and actionable.

