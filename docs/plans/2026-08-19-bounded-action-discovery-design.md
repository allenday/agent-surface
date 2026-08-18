# Bounded Action Discovery and Reference Codecs Design

## Purpose and users

Agent-surface should turn registered operations and deliberately marked Python methods into useful
next actions without traversing an application object graph or serializing every possible binding.
Library authors need stable command-slot identity for domain objects, while agents need a small
immediate action frontier with a deterministic path to every omitted action.

This issue adds transport-neutral reference, compilation, publication, and discovery primitives.
The generated Click and MCP adapters will project these primitives in later issues.

## Chosen approach

Candidate compilation is narrow and publication is explicit:

1. Registered operations contribute candidates from their Pydantic request fields.
2. Methods contribute candidates only when decorated with `@action`.
3. Compilation reads class dictionaries, callable signatures, and Pydantic `model_fields`; it never
   invokes a property, descriptor, or arbitrary attribute.
4. Runtime binding considers only ordinary instance data from `vars(instance)` and declared
   Pydantic fields.
5. Exact field-name plus compatible type may bind a slot. Type-only matching is disabled.
6. A required deny-by-default publication policy decides whether a compiled candidate is emitted.
7. Custom objects require an explicit reference codec before they can become command-slot values.

This retains useful introspection without making reflection itself an authorization mechanism.

## Reference contracts

`ReferenceCodec[T]` is a runtime protocol with:

- `kind: str`, the stable reference namespace
- `python_type: type[T]`, matched exactly to avoid subclass ambiguity
- `encode(value: T) -> str`, the stable command token
- `decode(token: str) -> T`, the round-trip inverse
- `display(value: T) -> str`, a human-facing label that is never used as identity

`ReferenceValue` is the structured projection:

```yaml
{kind: resource, id: resource-017, label: Production database}
```

`ReferenceRegistry` rejects duplicate kinds and Python types. `encode` and `decode` verify that a
codec round-trips the stable token. Built-in scalar slot values (`str`, `int`, finite `float`,
`bool`, `None`, and string-valued enums) use canonical tokens directly. Every other object raises
`MissingReferenceCodec`; `str(object)` is never a fallback. Display text is optional structured
metadata and never appears in a command token unless it is also the codec's explicit encoded ID.

## Candidate compilation

`ActionCandidate` and `ActionSlotPlan` are immutable runtime plans rather than transport models. A
slot plan retains its name, annotation, required/default state, and any explicit parameter-source
metadata. Python types remain in the plan and are not serialized.

`ActionCompiler` accepts an `OperationRegistry`:

- `compile_operations()` produces one candidate per registered operation in deterministic operation
  name order. Pydantic request fields become slots in declared field order.
- `compile_object(instance)` scans functions stored in class dictionaries across the MRO and keeps
  only methods marked by `@action(operation=..., rel=...)`. It inspects signatures without calling
  the method or reading descriptors. `self` is excluded; variadic parameters are rejected.
- A decorated method must target a registered operation. Invalid or ambiguous signatures fail at
  compilation with stable action-definition errors.

The decorator stores inert metadata on the function. Decoration does not register, execute, or
publish the method.

## Policy-gated binding and publication

`ActionPublisher` requires all of the following constructor inputs:

- a `ReferenceRegistry`
- a publication policy callable
- an operation-to-argv projector (default: split dotted operation names)

There is no permissive default policy. `DenyAllActions` is the default object when a caller asks for
one explicitly; `AllowActions` provides a small allow-list convenience policy.

For an allowed candidate, binding precedence is:

1. explicit values supplied by the caller
2. exact-name compatible values from safe instance data
3. declared parameter defaults
4. an unbound typed slot

An incompatible exact-name value stays unbound; the publisher does not search by type. A custom
bound object without a codec fails with `missing_reference_codec`. Fully bound actions receive a
concrete `command`; actions with unresolved slots receive `command_template` placeholders and typed
slot descriptions. A paginated parameter source is represented once on the slot, never expanded
into a Cartesian product.

Example template:

```yaml
rel: inspect-resource
command_template: [resource, inspect, "{ref}"]
slots:
  ref:
    type: reference
    reference_kind: resource
    source:
      command: [resource, list, --cursor, page-2, --limit, "20"]
```

## Bounded discovery

`ActionCatalog` stores an already policy-filtered, deterministic tuple of `Action` values. It never
stores or traverses an object graph. `page(cursor=None, budget=OutputBudget())` returns an
`ActionCollection` with no more than `budget.max_items` actions.

Cursors are opaque URL-safe tokens containing a version and the next numeric offset. Invalid,
out-of-range, or stale-version cursors fail with stable `invalid_action_cursor`. A truncated page
contains exactly one `discover` action pointing to the immediate next page. It does not enumerate
later pages. The collection reports `total`, `returned`, and `truncated`, so every omitted action is
reachable without appearing in the current response.

The renderer from issue #3 applies the final UTF-8 byte budget. A normal high-branch-factor fixture
must fit the default 20-item and 65,536-byte limits. If one action itself makes a page too large,
`render_envelope` returns `response_too_large`; the catalog never removes it silently.

## Data flow

```text
registered operations + decorated signatures
                    |
             ActionCompiler
                    |
       immutable action candidates
                    |
    explicit policy + safe values + codecs
                    |
             ActionPublisher
                    |
       concrete actions or templates
                    |
              ActionCatalog
                    |
      bounded frontier / cursor page
                    |
          YAML or JSON renderer
```

## Planned command tree and discovery

```text
<app> <operation> [bound arguments]
<app> actions list [--cursor CURSOR] [--limit INTEGER]
<app> actions explain OPERATION [--for REF]
<app> references decode KIND TOKEN
```

Representative future commands:

```text
inventory resource inspect resource-017
inventory resource mutate resource-017 --confirm true
inventory actions list --cursor YTE6MjA --limit 20
inventory actions explain resource.mutate --for resource-017
```

The framework API in this issue produces the command arrays; it does not add these Click commands
yet.

## Success and error contracts

Published actions use the existing `Action` and `ActionCollection` models. A bounded frontier is
rendered inside the existing envelope:

```yaml
next_actions:
  items:
    - {rel: inspect-resource, command: [resource, inspect, resource-017]}
  total: 400
  returned: 1
  truncated: true
  discover:
    rel: next-page
    command: [actions, list, --cursor, YTE6MQ, --limit, "20"]
```

Stable failures include:

- `missing_reference_codec`
- `duplicate_reference_codec`
- `invalid_reference`
- `invalid_action_signature`
- `unknown_action_operation`
- `invalid_action_cursor`

These transport-neutral exceptions expose a stable code, message, details, and repair guidance for
future adapter translation.

## Testing

Tests will cover:

- codec encode/decode round trips and independent display labels
- rejection of duplicate codecs, invalid round trips, and incidental object stringification
- deterministic operation candidate order and Pydantic field order
- decorated-method compilation without descriptor evaluation
- rejection of variadic and unknown-operation signatures
- deny-by-default policy and explicit allow-list publication
- exact-name compatible binding, defaults, unbound slots, and type-only non-binding
- canonical scalar command tokens and structured custom references
- parameterized templates with paginated slot sources
- 400-action fixtures returning bounded pages with only immediate continuation
- cursor validation, complete reachability, item budgets, byte budgets, YAML round trips, and no
  ellipsis placeholders
