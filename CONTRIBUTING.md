# Contributing

Focused issues and pull requests are welcome. For substantial changes, open an issue or discussion
first so the operation contract and adapter boundaries can be agreed before implementation.

## Development

Install [uv](https://docs.astral.sh/uv/), clone the repository, and create the locked Python 3.12+
environment:

```bash
uv sync --frozen --all-extras --dev
make check
```

Write a failing test before changing behavior. Keep CLI and MCP adapters thin, preserve structured
error codes, and follow the YAML and bounded-discovery rules in [AGENTS.md](AGENTS.md).

## Pull requests

- Keep unrelated changes separate.
- Explain the user-visible contract change and its motivation.
- Add or update tests and documentation together with the code.
- Run `make check` and include any platform-specific limitations in the PR description.
- Use a concise imperative commit message, such as `feat: add bounded action discovery`.

By contributing, you agree that your contribution is licensed under the MIT License.
