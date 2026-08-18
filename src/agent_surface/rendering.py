"""Deterministic human-readable and machine-readable document rendering."""

import json
from collections.abc import Mapping, Sequence
from io import StringIO
from typing import Any, Literal

from pydantic import Field, TypeAdapter
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import LiteralScalarString

from agent_surface.budgets import OutputBudget, OutputBudgetExceeded
from agent_surface.contracts import (
    ContractModel,
    ErrorDetail,
    ErrorEnvelope,
    ErrorInfo,
    SuccessEnvelope,
)

DocumentFormat = Literal["yaml", "json"]
YamlStyle = Literal["auto", "flow", "block"]

_AUTO_FLOW_MAX_ITEMS = 6
_AUTO_FLOW_MAX_WIDTH = 100
_JSON_VALUE = TypeAdapter(Any)


class RenderOptions(ContractModel):
    """Format, presentation style, and limits for one rendered document."""

    format: DocumentFormat = "yaml"
    yaml_style: YamlStyle = "auto"
    budget: OutputBudget = Field(default_factory=OutputBudget)


def render(value: Any, *, options: RenderOptions | None = None) -> str:
    """Render one complete JSON-compatible value without mutating its semantics."""

    selected = options or RenderOptions()
    normalized = _JSON_VALUE.dump_python(value, mode="json")
    _validate_item_budget(normalized, selected.budget)
    if selected.format == "json":
        document = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    else:
        document = _render_yaml(normalized, selected.yaml_style)
    _validate_byte_budget(document, selected.budget)
    return document


def render_envelope(
    envelope: SuccessEnvelope[Any] | ErrorEnvelope,
    *,
    options: RenderOptions | None = None,
) -> str:
    """Render an envelope, substituting a complete structured budget error when possible."""

    selected = options or RenderOptions()
    try:
        return render(envelope, options=selected)
    except OutputBudgetExceeded as original:
        error_envelope = ErrorEnvelope(
            command=envelope.command,
            error=ErrorInfo(
                code=original.code,
                message=str(original),
                details=(
                    ErrorDetail(
                        path=original.path,
                        code=original.code,
                        value=original.details,
                    ),
                ),
            ),
            fix=original.fix,
        )
        try:
            return render(error_envelope, options=selected)
        except OutputBudgetExceeded as fallback:
            raise original from fallback


def _validate_item_budget(
    value: Any,
    budget: OutputBudget,
    path: tuple[str | int, ...] = (),
) -> None:
    if _is_sequence(value):
        if (not path or path[-1] == "items") and len(value) > budget.max_items:
            raise OutputBudgetExceeded(
                code="item_budget_exceeded",
                message="Collection exceeds the item budget",
                path=path,
                details={"returned": len(value), "max_items": budget.max_items},
                fix="Use a bounded collection with a continuation action.",
            )
        for index, item in enumerate(value):
            _validate_item_budget(item, budget, (*path, index))
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_item_budget(item, budget, (*path, str(key)))


def _validate_byte_budget(document: str, budget: OutputBudget) -> None:
    measured = len(document.encode("utf-8"))
    if measured > budget.max_bytes:
        raise OutputBudgetExceeded(
            code="response_too_large",
            message="Rendered response exceeds the byte budget",
            details={"measured_bytes": measured, "max_bytes": budget.max_bytes},
            fix="Retry with a lower item limit or a narrower detail level.",
        )


def _render_yaml(value: Any, style: YamlStyle) -> str:
    yaml = YAML()
    yaml.allow_unicode = True
    yaml.width = 4096
    yaml.default_flow_style = None
    stream = StringIO()
    yaml.dump(_styled_value(value, style), stream)
    return stream.getvalue()


def _styled_value(value: Any, style: YamlStyle) -> Any:
    if isinstance(value, Mapping):
        mapping = CommentedMap(
            (key, _styled_value(item, style)) for key, item in value.items()
        )
        _set_collection_style(mapping, value, style)
        return mapping
    if _is_sequence(value):
        sequence = CommentedSeq(_styled_value(item, style) for item in value)
        _set_collection_style(sequence, value, style)
        return sequence
    if isinstance(value, str) and "\n" in value and style != "flow":
        return LiteralScalarString(value)
    return value


def _set_collection_style(
    rendered: CommentedMap | CommentedSeq,
    original: Mapping[str, Any] | Sequence[Any],
    style: YamlStyle,
) -> None:
    if style == "flow" or (style == "auto" and _eligible_for_auto_flow(original)):
        rendered.fa.set_flow_style()
    else:
        rendered.fa.set_block_style()


def _eligible_for_auto_flow(value: Mapping[str, Any] | Sequence[Any]) -> bool:
    if len(value) > _AUTO_FLOW_MAX_ITEMS:
        return False
    items = value.values() if isinstance(value, Mapping) else value
    if any(_is_collection(item) or _is_multiline(item) for item in items):
        return False
    return len(_isolated_flow_yaml(value).rstrip("\n")) <= _AUTO_FLOW_MAX_WIDTH


def _isolated_flow_yaml(value: Mapping[str, Any] | Sequence[Any]) -> str:
    yaml = YAML(typ="safe", pure=True)
    yaml.allow_unicode = True
    yaml.default_flow_style = True
    yaml.width = 4096
    stream = StringIO()
    yaml.dump(value, stream)
    return stream.getvalue()


def _is_collection(value: Any) -> bool:
    return isinstance(value, Mapping) or _is_sequence(value)


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _is_multiline(value: Any) -> bool:
    return isinstance(value, str) and "\n" in value


__all__ = ["RenderOptions", "render", "render_envelope"]
