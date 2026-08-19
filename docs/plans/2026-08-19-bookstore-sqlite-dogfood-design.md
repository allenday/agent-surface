# SQLite Bookstore Dogfood Design

## Purpose

Make the bookstore a persistent, complete CRUD example and connect its MCP projection to real Codex
and Claude Code clients. The example remains intentionally small: books are fixed seed data and only
holds are persisted.

## Domain and storage

SQLite from the Python standard library stores `id`, `book`, and `status` for each hold. The stable
hold ID remains `hold_<book reference>`. Creating a duplicate returns `hold_exists`; no time-to-live,
clock, or background expiration behavior is introduced.

The operations are:

- `holds.create`: insert an active hold;
- `holds.get`: read a hold;
- `holds.cancel`: update its status to `cancelled`;
- `holds.delete`: permanently remove it.

`build_surface()` defaults to an in-memory database for isolated embedding and tests. Executable CLI
and MCP entry points use `AGENT_SURFACE_BOOKSTORE_DB`, falling back to an XDG-style user data path.
Tests always supply a temporary path.

## Navigation

The demonstrated trajectory is `books.search` → `books.inspect` → `holds.create` → `holds.get` or
`holds.cancel` → `holds.delete`. Every transition remains a concrete bounded action. Click follows
`command`; MCP follows `operation` plus `bound`.

## Client integration

An executable `examples/bookstore-mcp` wrapper starts the stdio server without writing protocol data
outside stdout. Documentation includes an exact Codex `config.toml` table and CLI registration, plus
the equivalent Claude Code user-scoped command and `.mcp.json` shape. Absolute paths make process
startup independent of a client's working directory. The repository's own Codex configuration will
register this wrapper after merged code is present at its stable checkout path.

## Verification

Tests prove persistence across separate surface instances, duplicate and missing errors, all four
CRUD operations through MCP, real stdio startup, documentation links, and configuration examples.
The local Codex registration is verified with `codex mcp get bookstore`; a restarted session is then
needed for the desktop client to attach the newly configured server.
