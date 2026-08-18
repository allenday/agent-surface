"""Transport-neutral bounded operation discovery."""

import base64
import binascii
from typing import Any, Self

from pydantic import Field, model_validator

from agent_surface.budgets import OutputBudget
from agent_surface.contracts import Action, ContractModel
from agent_surface.operations import OperationDefinition, OperationError, OperationRegistry


class OperationSummary(ContractModel):
    name: str
    summary: str = ""
    read_only: bool = False
    destructive: bool = False
    idempotent: bool = False
    open_world: bool = False


class OperationDescription(OperationSummary):
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class OperationPage(ContractModel):
    items: tuple[OperationSummary, ...] = ()
    total: int = Field(ge=0)
    returned: int = Field(ge=0)
    truncated: bool = False
    continuation: Action | None = None

    @model_validator(mode="after")
    def validate_page(self) -> Self:
        if self.returned != len(self.items):
            raise ValueError("returned must equal the number of items")
        if self.total < self.returned:
            raise ValueError("total must be greater than or equal to returned")
        if self.truncated != (self.continuation is not None):
            raise ValueError("continuation is required exactly when truncated")
        return self


class InvalidOperationCursor(OperationError):
    def __init__(self) -> None:
        super().__init__(
            "invalid_operation_cursor",
            "Operation cursor is invalid or out of range",
            fix="Restart operation discovery without a cursor.",
        )


class OperationCatalog:
    def __init__(
        self,
        operations: OperationRegistry,
        *,
        discovery_command: tuple[str, ...],
    ) -> None:
        self._operations = operations
        self._definitions = operations.list()
        self._discovery_command = discovery_command

    def page(
        self,
        *,
        cursor: str | None = None,
        budget: OutputBudget | None = None,
    ) -> OperationPage:
        selected = budget or OutputBudget()
        offset = 0 if cursor is None else _decode_cursor(cursor)
        if cursor is not None and offset >= len(self._definitions):
            raise InvalidOperationCursor()
        definitions = self._definitions[offset : offset + selected.max_items]
        next_offset = offset + len(definitions)
        truncated = next_offset < len(self._definitions)
        continuation = None
        if truncated:
            continuation = Action(
                rel="next-page",
                description="Return the next page of registered operations",
                command=(
                    *self._discovery_command,
                    "--cursor",
                    _encode_cursor(next_offset),
                    "--limit",
                    str(selected.max_items),
                ),
            )
        return OperationPage(
            items=tuple(_summary(definition) for definition in definitions),
            total=len(self._definitions),
            returned=len(definitions),
            truncated=truncated,
            continuation=continuation,
        )

    def describe(self, name: str) -> OperationDescription:
        definition = self._operations.describe(name)
        return OperationDescription(
            **_summary(definition).model_dump(),
            input_schema=definition.input_model.model_json_schema(mode="validation"),
            output_schema=definition.output_model.model_json_schema(mode="serialization"),
        )


def _summary(definition: OperationDefinition) -> OperationSummary:
    return OperationSummary(
        name=definition.name,
        summary=definition.summary,
        read_only=definition.read_only,
        destructive=definition.destructive,
        idempotent=definition.idempotent,
        open_world=definition.open_world,
    )


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"v1:{offset}".encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> int:
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(cursor + padding, altchars=b"-_", validate=True).decode()
        version, raw_offset = decoded.split(":", 1)
        offset = int(raw_offset)
        if version != "v1" or offset < 0:
            raise ValueError
        return offset
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise InvalidOperationCursor() from error


__all__ = [
    "InvalidOperationCursor",
    "OperationCatalog",
    "OperationDescription",
    "OperationPage",
    "OperationSummary",
]
