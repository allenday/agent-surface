# Typed App composition design

## Goal

Release `0.2.0` with one generated Click tree and one MCP server assembled from independently typed `App` instances. A mount routes only its own operations and preserves the child application's request model, shared inputs, reference registry, action provider, canonical envelope renderer, and validation behavior.

## Decision

Introduce a transport-neutral composition object that owns an ordered mapping of mount prefixes to child application surfaces. A mounted surface is an `App` plus its projection configuration. The composed object validates its complete operation-path set before either adapter is built.

`App` remains the unit that owns operation registration and Pydantic validation. Composition never merges child request models or shared-input models. It prefixes a child's operation paths for public routing; the child still receives its original operation name and payload. This lets `diagram render` inherit the render child’s registry inputs while `diagram project` accepts only the project child’s declared `source` input.

## Public API

The public root builder exposes `mount(prefix, app, ...)` and returns a composed surface suitable for both adapters. The exact configuration arguments mirror the existing adapter inputs: references, action provider, render options, envelope renderer, and Click operation-error exit policy. A mount prefix is one or more non-empty command segments.

The composed surface exposes:

- one deterministic operation catalog with public paths prefixed by their mount;
- one composed manifest with child provenance and public operation paths;
- `click()` and `mcp()` sibling projections that dispatch to the same mount table.

Composition rejects duplicate paths and prefix collisions deterministically before a server or command tree is exposed. A leaf at `diagram` therefore cannot coexist with `diagram project`; sibling leaves `diagram render` and `diagram project` are supported.

## Adapter behavior

Click builds groups from public prefixed paths, then resolves a leaf to its child projection. Only that child’s shared fields appear on and are read from its leaf/root scope. MCP exposes prefixed tool names and delegates each call to the matching child adapter, preserving the child’s schema, output budget, references, actions, renderer, and error policy.

Discovery returns public prefixed names and remains bounded. Canonical envelopes continue to receive the child operation definition and redacted child request. Manifests preserve child distribution/factory provenance while reporting the public mounted path; verification rejects a child that no longer matches its declared manifest.

## Documentation and release

Document the composition API in the Python API reference and MCP contract, with a runnable Click/MCP example showing isolated sibling shared inputs. Add a concept page explaining when to use composition rather than one `App(shared_input_model=...)`. Bump package metadata and package tests to `0.2.0`; release only after the full GitHub Actions gate, GitHub Release, and PyPI OIDC publish succeed.

## Acceptance basis

1. Click and MCP expose the same prefixed public operations from two child Apps.
2. A child’s shared input is never accepted, rendered, or supplied to another child.
3. Prefix/duplicate collisions fail deterministically.
4. Discovery, manifests, canonical envelopes, references, actions, and parse errors retain their existing contracts under composition.
5. Docs examples run against the public API, and `0.2.0` is built and published through the existing release workflow.
