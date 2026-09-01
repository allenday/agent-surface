# Operation manifests

An operation manifest lets a host discover installed Agent Surface applications without importing
their plugin code. It is generated from the authoritative `App` registry at wheel-build time and
stored as `agent-surface-operations.json` in the wheel's `.dist-info` directory.

Each manifest contains versioned app and wheel-distribution identities, its explicit execution
factory, and sorted operations. An operation records its exact path tokens, summary, four safety
annotations, and Pydantic validation and serialization JSON Schemas. Discovery validates the full
v1 contract and that the recorded distribution identity matches the installed wheel.

## Publish a manifest with Hatch

Put `agent-surface` in the build environment, then configure the explicit factory. The hook imports
only that factory while building; ordinary installed discovery never imports it.

```toml
[build-system]
requires = ["hatchling>=1.32", "agent-surface>=0.1.7"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.agent-surface]
factory = "my_operations.surface:build_app"
```

`build_app` must return an `App`. The hook searches the project root and `src/` by default. Set
`source` to one path or a list of paths when the factory lives elsewhere.

```toml
[tool.hatch.build.hooks.agent-surface]
factory = "my_operations.surface:build_app"
source = ["lib"]
```

The build environment must also contain any dependencies imported by that factory.

## Discover, then execute safely

Hosts use `installed_manifests()` for import-free discovery. It rejects duplicate and
prefix-colliding paths deterministically, so all discovered operations can mount beneath one CLI or
MCP command tree.

```python
from agent_surface import installed_manifests, verify_manifest

manifests = installed_manifests()  # reads wheel metadata; imports no plugin code
manifest = next(item for item in manifests if item["app"]["name"] == "my-operations")

# Only after selecting an operation, import manifest["factory"] using the host's own boundary.
app = build_app()
verify_manifest(app, manifest)  # fail closed if the registry, schemas, or path changed
```

`verify_manifest()` compares the complete regenerated manifest, which is stronger than checking
only the selected operation: substituted wheels, renamed paths, annotation changes, and schema
drift all fail before execution.
