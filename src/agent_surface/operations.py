"""Typed operation registration and invocation."""

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, get_type_hints

from pydantic import BaseModel, ValidationError


class OperationError(Exception):
    """Expected, machine-readable operation failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: tuple[dict[str, Any], ...] = (),
        fix: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.fix = fix
        self.retryable = retryable


class DuplicateOperationError(OperationError):
    def __init__(self, name: str) -> None:
        super().__init__("duplicate_operation", f"Operation is already registered: {name}")


class UnknownOperationError(OperationError):
    def __init__(self, name: str) -> None:
        super().__init__("unknown_operation", f"Unknown operation: {name}")


class OperationInputError(OperationError):
    def __init__(self, name: str, error: ValidationError) -> None:
        details = tuple(dict(item) for item in error.errors(include_url=False))
        super().__init__("invalid_input", f"Invalid input for operation {name}", details=details)


class OperationOutputError(OperationError):
    def __init__(self, name: str, error: ValidationError) -> None:
        details = tuple(dict(item) for item in error.errors(include_url=False))
        super().__init__("invalid_output", f"Invalid output from operation {name}", details=details)


OperationHandler = Callable[[BaseModel], BaseModel | Mapping[str, Any] | Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class OperationDefinition:
    name: str
    summary: str
    handler: OperationHandler
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    read_only: bool = False
    destructive: bool = False
    idempotent: bool = False
    open_world: bool = False


class OperationRegistry:
    """Deterministic registry of typed application operations."""

    def __init__(self) -> None:
        self._operations: dict[str, OperationDefinition] = {}

    def register(
        self,
        name: str,
        handler: OperationHandler,
        *,
        summary: str = "",
        read_only: bool = False,
        destructive: bool = False,
        idempotent: bool = False,
        open_world: bool = False,
    ) -> OperationDefinition:
        if name in self._operations:
            raise DuplicateOperationError(name)

        signature = inspect.signature(handler)
        parameters = tuple(signature.parameters.values())
        hints = get_type_hints(handler)
        if len(parameters) != 1:
            raise TypeError("Operation handlers must accept exactly one Pydantic request model")

        input_model = hints.get(parameters[0].name)
        output_model = hints.get("return")
        if not inspect.isclass(input_model) or not issubclass(input_model, BaseModel):
            raise TypeError("Operation request annotation must be a Pydantic model")
        if not inspect.isclass(output_model) or not issubclass(output_model, BaseModel):
            raise TypeError("Operation return annotation must be a Pydantic model")

        definition = OperationDefinition(
            name=name,
            summary=summary or inspect.getdoc(handler) or "",
            handler=handler,
            input_model=input_model,
            output_model=output_model,
            read_only=read_only,
            destructive=destructive,
            idempotent=idempotent,
            open_world=open_world,
        )
        self._operations[name] = definition
        return definition

    def describe(self, name: str) -> OperationDefinition:
        try:
            return self._operations[name]
        except KeyError as error:
            raise UnknownOperationError(name) from error

    def list(self) -> tuple[OperationDefinition, ...]:
        return tuple(self._operations[name] for name in sorted(self._operations))

    def validate(
        self,
        definition: OperationDefinition,
        payload: Any,
    ) -> BaseModel:
        """Validate one payload before a sibling transport invokes its handler."""
        try:
            return definition.input_model.model_validate(payload)
        except ValidationError as error:
            raise OperationInputError(definition.name, error) from error

    async def invoke_request(
        self,
        definition: OperationDefinition,
        request: BaseModel,
    ) -> BaseModel:
        """Invoke one already-validated request through the registered handler."""

        result = definition.handler(request)
        if inspect.isawaitable(result):
            result = await result

        try:
            return definition.output_model.model_validate(result)
        except ValidationError as error:
            raise OperationOutputError(definition.name, error) from error

    async def invoke(self, name: str, payload: Any) -> BaseModel:
        definition = self.describe(name)
        request = self.validate(definition, payload)
        return await self.invoke_request(definition, request)


__all__ = [
    "DuplicateOperationError",
    "OperationDefinition",
    "OperationError",
    "OperationInputError",
    "OperationOutputError",
    "OperationRegistry",
    "UnknownOperationError",
]
