# Bookstore contextual action descriptions

## Purpose

Make every contextual bookstore action self-explanatory to humans and agents. Live MCP dogfooding
showed that actions returned after `holds.cancel` had correct `rel`, `operation`, and `bound` fields
but empty descriptions.

## Design

Keep descriptions explicit where `BookstoreActions.actions_for()` constructs each action. This
matches the existing create response and lets copy describe the current state transition. Do not
derive descriptions from generic operation summaries or add a separate label registry.

Cover all hold-result branches: reading an active hold, cancelling a hold, reading a cancelled hold,
deleting a hold, and inspecting the book after deletion. Tests assert that every contextual action
returned by create, get, cancel, and delete has a non-empty description.

No operation names, schemas, persistence semantics, or wire structure change.
