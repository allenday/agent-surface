# Reference Consumer Conformance Design

## Goal

Create a demanding but generic consumer fixture that drives agent-surface adapters without
identifying, importing, or copying any external project. The fixture proves that applications can
adopt the library behind an internal boundary while retaining ownership of domain models, errors,
and behavior.

## Boundary

The fixture has two layers:

- `domain.py` contains consumer-owned Pydantic requests/results, domain exceptions, and sync/async
  services. It never imports `agent_surface`.
- `integration.py` imports both sides, registers existing service methods, translates domain
  exceptions into stable operation errors, and attaches surface metadata.

This is the recommended adoption pattern. Applications do not subclass agent-surface contracts in
their domain layer and do not route MCP through Click or Click through MCP.

## Scenarios

The fixture covers the constraints future adapters must preserve:

- a read-only lookup with a stable object reference;
- an asynchronous bounded listing with total/returned/truncated metadata;
- a destructive mutation requiring explicit confirmation metadata;
- a sensitive input annotated for command-context redaction;
- a consumer-owned exception translated at the integration boundary;
- Pydantic validation for both inputs and results.

All names and values are synthetic and generic. No external repository, URL, identifier, schema,
or fixture data is included.

## Conformance contract

The first implementation tests direct registry behavior and records reusable expected operation
metadata. Subsequent YAML, Click, and MCP issues extend the same suite rather than inventing
adapter-specific examples.

Conformance means:

1. domain modules contain no agent-surface dependency;
2. every transport invokes the same registered handler and Pydantic models;
3. operation identity, safety flags, error codes, and bounded result semantics remain equivalent;
4. sensitive values never appear in rendered command context;
5. stable references use explicit codecs rather than object stringification.

Items 4 and 5 are recorded as required adapter behavior and become executable when their
foundational issues land.

## Non-goals

- Importing or testing against an external consumer repository.
- Reproducing a consumer's domain vocabulary or complete command tree.
- Expanding Python support below the package's 3.12 baseline.
- Implementing YAML, Click, MCP, discovery, or reference codecs in this issue.
