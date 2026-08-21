# README MCP Mode Design

## Goal

Correct the HATEOAS citation and make the first MCP integration use one executable file, then ship
the immutable correction as version 0.1.2.

## Decisions

- Link HATEOAS to <https://en.wikipedia.org/wiki/HATEOAS>, as requested; the previous Fielding
  anchor identified the unrelated Components section.
- Replace `hello_mcp.py` with `hello.py --mcp`. The program dispatches that exact argv sequence to
  `asyncio.run(mcp.run_stdio())`; all other argv remains Click-owned.
- Codex and Claude configuration invoke the same Python file with `--mcp`.
- Retain `v0.1.1`: it is an already-public GitHub Release and TestPyPI artifact. Its production
  PyPI workflow is cancelled. Publish the correction as 0.1.2 instead.

## Verification

Repository metadata tests assert the URL, one-file MCP command, and 0.1.2 version. `make check`
validates the final package. TestPyPI and PyPI will each receive a clean-install smoke test.
