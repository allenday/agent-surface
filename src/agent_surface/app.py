"""Top-level application registry."""

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from agent_surface.operations import OperationHandler, OperationRegistry

HandlerT = TypeVar("HandlerT", bound=OperationHandler)


class App:
    """A typed application surface shared by all adapters."""

    def __init__(self, name: str, *, version: str = "0.1.0") -> None:
        self.name = name
        self.version = version
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
