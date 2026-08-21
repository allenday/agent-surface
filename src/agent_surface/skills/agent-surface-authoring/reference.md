# Agent-Surface Authoring Reference

## Minimal integration shape

```python
from pydantic import BaseModel, ConfigDict, Field

from agent_surface import App, OperationError, ReferenceRegistry
from agent_surface.adapters.click import build_click_group
from agent_surface.adapters.mcp import MCPAdapter


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WidgetRef(Model):
    value: str = Field(min_length=1, max_length=128)


class WidgetRefCodec:
    kind = "widget"
    python_type = WidgetRef

    def encode(self, value: WidgetRef) -> str:
        return value.value

    def decode(self, token: str) -> WidgetRef:
        return WidgetRef(value=token)

    def display(self, value: WidgetRef) -> str:
        return value.value


class InspectRequest(Model):
    widget: WidgetRef


class Widget(Model):
    ref: WidgetRef
    title: str


service = make_consumer_owned_service()
references = ReferenceRegistry()
references.register(WidgetRefCodec())
app = App("widgets")


@app.operation("widgets.inspect", summary="Inspect one widget", read_only=True)
def inspect_widget(request: InspectRequest) -> Widget:
    try:
        return service.inspect(request.widget)
    except WidgetMissing as error:
        raise OperationError(
            "widget_not_found",
            "Widget was not found",
            details=({"widget": request.widget.value},),
            fix="Choose a widget reference returned by widgets.search.",
        ) from error


cli = build_click_group(app, references=references)
mcp = MCPAdapter(app, references=references)
```

`make_consumer_owned_service` and `WidgetMissing` are placeholders for the host application. The
wrapper—not the domain layer—is the transport boundary.

## Action and output checklist

| Need | Contract |
| --- | --- |
| One valid immediate transition | A concrete `rel`, description, operation, and bound values |
| Many possible children | A bounded sample plus a discover action or parameterized template |
| Next page | Only the immediate cursor continuation |
| List result | Truthful `total`, `returned`, and `truncated` fields |
| Large response | `OutputBudget` / `BoundedCollection` and a structured limit outcome |
| Write | `confirm: bool = False` and an explicit confirmation action |

## Verification matrix

1. Test request validation and the consumer-owned service wrapper.
2. Test reference encode/decode and rejection of unknown or malformed tokens.
3. Test state-specific actions, descriptions, write confirmation, and bounded discovery.
4. Test Click success and repair-oriented error envelopes as YAML.
5. Test MCP tool schema, invocation, annotations, and structured content for the same operation.
6. Run `make check`, build the wheel, install it in a clean environment, and use
   `bundled_skill_path("agent-surface-authoring")` to verify both sidecar files.
