"""Typed operation registration and invocation."""

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, get_args, get_origin, get_type_hints

from pydantic import BaseModel, ValidationError


@dataclass(frozen=True, slots=True)
class OperationOutcome[ResultT: BaseModel]:
    """A valid domain result with an explicit bounded process classification."""

    result: ResultT
    exit_code: int = 0

    def __post_init__(self) -> None:
        if type(self.exit_code) is not int or not 0 <= self.exit_code <= 125:
            raise ValueError("OperationOutcome.exit_code must be an integer from 0 through 125")


@dataclass(frozen=True, slots=True)
class _OperationInvocation:
    """Internal validated result and its transport-neutral exit classification."""

    result: BaseModel
    exit_code: int = 0

    def __post_init__(self) -> None:
        if type(self.exit_code) is not int or not 0 <= self.exit_code <= 125:
            raise ValueError("Operation invocation exit_code must be an integer from 0 through 125")


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


OperationHandler = Callable[
    [BaseModel], BaseModel | OperationOutcome[BaseModel] | Mapping[str, Any] | Awaitable[Any]
]


@dataclass(frozen=True, slots=True)
class OperationDefinition:
    name: str
    summary: str
    handler: OperationHandler
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    returns_outcome: bool = False
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
        output_model, returns_outcome = _output_model(hints.get("return"))
        if not inspect.isclass(input_model) or not issubclass(input_model, BaseModel):
            raise TypeError("Operation request annotation must be a Pydantic model")

        definition = OperationDefinition(
            name=name,
            summary=summary or inspect.getdoc(handler) or "",
            handler=handler,
            input_model=input_model,
            output_model=output_model,
            returns_outcome=returns_outcome,
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

        return (await self._invoke_request_with_outcome(definition, request)).result

    async def _invoke_request_with_outcome(
        self,
        definition: OperationDefinition,
        request: BaseModel,
    ) -> _OperationInvocation:
        """Invoke one request while retaining an explicit successful exit classification."""

        result = definition.handler(request)
        if inspect.isawaitable(result):
            result = await result

        exit_code = 0
        if isinstance(result, OperationOutcome):
            if not definition.returns_outcome:
                raise OperationError(
                    "invalid_outcome",
                    f"Operation {definition.name} returned an undeclared OperationOutcome",
                )
            exit_code = result.exit_code
            result = result.result
        elif definition.returns_outcome:
            raise OperationError(
                "invalid_outcome",
                f"Operation {definition.name} must return an OperationOutcome",
            )

        try:
            validated = definition.output_model.model_validate(result)
        except ValidationError as error:
            raise OperationOutputError(definition.name, error) from error
        return _OperationInvocation(result=validated, exit_code=exit_code)

    async def invoke(self, name: str, payload: Any) -> BaseModel:
        definition = self.describe(name)
        request = self.validate(definition, payload)
        return await self.invoke_request(definition, request)


def _output_model(annotation: Any) -> tuple[type[BaseModel], bool]:
    if get_origin(annotation) is OperationOutcome:
        arguments = get_args(annotation)
        if len(arguments) == 1 and inspect.isclass(arguments[0]) and issubclass(
            arguments[0], BaseModel
        ):
            return arguments[0], True
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        return annotation, False
    raise TypeError(
        "Operation return annotation must be a Pydantic model or OperationOutcome[Model]"
    )


__all__ = [
    "DuplicateOperationError",
    "OperationDefinition",
    "OperationError",
    "OperationInputError",
    "OperationOutcome",
    "OperationOutputError",
    "OperationRegistry",
    "UnknownOperationError",
]
