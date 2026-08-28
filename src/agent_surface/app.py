"""Top-level application registry."""

import inspect
from collections.abc import Callable
from typing import Any, TypeVar, get_type_hints

from pydantic import BaseModel

from agent_surface.operations import OperationHandler, OperationRegistry

HandlerT = TypeVar("HandlerT", bound=OperationHandler)


class App:
    """A typed application surface shared by all adapters."""

    def __init__(
        self,
        name: str,
        *,
        version: str = "0.1.0",
        shared_input_model: type[BaseModel] | None = None,
    ) -> None:
        if shared_input_model is not None and not issubclass(shared_input_model, BaseModel):
            raise TypeError("shared_input_model must be a Pydantic model")
        self.name = name
        self.version = version
        self.shared_input_model = shared_input_model
        self.operations = OperationRegistry()

    def operation(
        self,
        name: str,
        *,
        summary: str = "",
        read_only: bool = False,
        destructive: bool = False,
        idempotent: bool = False,
        open_world: bool = False,
    ) -> Callable[[HandlerT], HandlerT]:
        def decorator(handler: HandlerT) -> HandlerT:
            if self.shared_input_model is not None:
                hints = get_type_hints(handler)
                parameters = tuple(inspect.signature(handler).parameters.values())
                request_model = hints.get(parameters[0].name) if parameters else None
                if not isinstance(request_model, type) or not issubclass(
                    request_model, self.shared_input_model
                ):
                    raise TypeError(
                        "Operation request models must inherit App.shared_input_model"
                    )
                overlap = set(request_model.__annotations__) & set(
                    self.shared_input_model.model_fields
                )
                if overlap:
                    raise TypeError(
                        "Operation request models may not override shared input fields: "
                        + ", ".join(sorted(overlap))
                    )
            self.operations.register(
                name,
                handler,
                summary=summary,
                read_only=read_only,
                destructive=destructive,
                idempotent=idempotent,
                open_world=open_world,
            )
            return handler

        return decorator

    async def invoke(self, name: str, payload: Any) -> BaseModel:
        return await self.operations.invoke(name, payload)


__all__ = ["App"]
