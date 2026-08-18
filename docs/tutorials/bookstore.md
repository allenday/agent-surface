# Bookstore tutorial

This tutorial follows one complete HATEOAS trajectory through the executable example in
[`examples/bookstore.py`](../../examples/bookstore.py). Start with only a search command; each
response supplies the valid next command.

## Run the example

From the repository root:

```bash
uv sync --frozen --all-extras --dev
./examples/bookstore books search --query dune --limit 2
```

The YAML response contains the matching books and a bounded `next_actions` collection. Follow the
returned `inspect` command verbatim:

```bash
./examples/bookstore books inspect --book book_dune
```

The detail response advertises `reserve` only when the book is available. That mutation is explicit
and confirmation-gated:

```bash
./examples/bookstore holds create --book book_dune --confirm
```

The resulting hold advertises the next valid transitions, such as inspecting its book or cancelling
the hold. The caller never needs to invent a route, stringify a Python object, or load the entire
application graph.

## Read the integration boundary

The example deliberately keeps four concerns visible:

- Pydantic request and result models describe domain data.
- `App` registers typed operations without Click imports in handlers.
- `BookRefCodec` gives object references stable wire identity.
- `BookstoreActions` chooses a small, relevant frontier for each result.

Read [`examples/bookstore.py`](../../examples/bookstore.py) from `build_surface()` outward, then see
[adopting an existing application](../how-to/adopt-an-existing-app.md) for the production pattern.

## Explore instead of guessing

The generated CLI includes machine-readable discovery:

```bash
./examples/bookstore operations list
./examples/bookstore operations describe books.search
./examples/bookstore actions list --operation books.inspect
```

Normal `--help` remains useful to humans. Discovery commands provide schemas, pagination, and stable
structured envelopes to agents. See the [CLI contract](../reference/cli-contract.md) for the exact
rules.

