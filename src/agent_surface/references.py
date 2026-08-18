"""Stable reference identity separate from human display text."""

import math
from enum import Enum
from typing import Any, Protocol

from agent_surface.contracts import ContractModel


class ReferenceCodec[T](Protocol):
    kind: str
    python_type: type[T]

    def encode(self, value: T) -> str: ...

    def decode(self, token: str) -> T: ...

    def display(self, value: T) -> str: ...


class ReferenceValue(ContractModel):
    kind: str
    id: str
    label: str | None = None


class ReferenceError(Exception):
    code: str

    def __init__(self, message: str, *, fix: str) -> None:
        super().__init__(message)
        self.fix = fix


class DuplicateReferenceCodec(ReferenceError):
    code = "duplicate_reference_codec"


class MissingReferenceCodec(ReferenceError):
    code = "missing_reference_codec"


class InvalidReference(ReferenceError):
    code = "invalid_reference"


class ReferenceRegistry:
    """Exact-type and kind lookup for explicitly registered reference codecs."""

    def __init__(self) -> None:
        self._by_type: dict[type[Any], ReferenceCodec[Any]] = {}
        self._by_kind: dict[str, ReferenceCodec[Any]] = {}

    def register[T](self, codec: ReferenceCodec[T]) -> None:
        if codec.kind in self._by_kind:
            raise DuplicateReferenceCodec(
                f"Reference codec kind is already registered: {codec.kind}",
                fix="Choose a unique stable reference kind.",
            )
        if codec.python_type in self._by_type:
            raise DuplicateReferenceCodec(
                f"Reference codec type is already registered: {codec.python_type.__name__}",
                fix="Register exactly one codec for each Python type.",
            )
        self._by_kind[codec.kind] = codec
        self._by_type[codec.python_type] = codec

    def encode(self, value: object) -> ReferenceValue:
        codec = self._by_type.get(type(value))
        if codec is None:
            raise MissingReferenceCodec(
                f"No reference codec is registered for {type(value).__name__}",
                fix="Register an explicit codec before binding this object to an action slot.",
            )
        token = codec.encode(value)
        decoded = codec.decode(token)
        if not isinstance(decoded, codec.python_type) or codec.encode(decoded) != token:
            raise InvalidReference(
                f"Reference codec {codec.kind} does not round-trip encoded values",
                fix="Make decode(encode(value)) preserve the encoded identity.",
            )
        return ReferenceValue(kind=codec.kind, id=token, label=codec.display(value))

    def decode(self, reference: ReferenceValue) -> Any:
        codec = self._by_kind.get(reference.kind)
        if codec is None:
            raise MissingReferenceCodec(
                f"No reference codec is registered for kind {reference.kind}",
                fix="Register the codec for this reference kind.",
            )
        value = codec.decode(reference.id)
        if not isinstance(value, codec.python_type) or codec.encode(value) != reference.id:
            raise InvalidReference(
                f"Reference {reference.kind}:{reference.id} failed codec round-trip validation",
                fix="Use an ID produced by the registered codec.",
            )
        return value

    def decode_type[T](self, python_type: type[T], token: str) -> T:
        """Decode one stable token using the codec registered for an exact Python type."""

        codec = self._by_type.get(python_type)
        if codec is None:
            raise MissingReferenceCodec(
                f"No reference codec is registered for {python_type.__name__}",
                fix="Register an explicit codec before decoding this reference token.",
            )
        value = codec.decode(token)
        if type(value) is not python_type or codec.encode(value) != token:
            raise InvalidReference(
                f"Reference {codec.kind}:{token} failed codec round-trip validation",
                fix="Use an ID produced by the registered codec.",
            )
        return value


def encode_scalar(value: object) -> str:
    """Encode safe scalar slot values without incidental object stringification."""

    if isinstance(value, Enum):
        if type(value.value) is str:
            return value.value
        return _unsupported_scalar(value)
    if type(value) is str:
        return value
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if type(value) is float and math.isfinite(value):
        return repr(value)
    if value is None:
        return "null"
    return _unsupported_scalar(value)


def _unsupported_scalar(value: object) -> str:
    raise MissingReferenceCodec(
        f"No scalar encoder or reference codec is available for {type(value).__name__}",
        fix="Register an explicit reference codec for custom slot values.",
    )


__all__ = [
    "DuplicateReferenceCodec",
    "InvalidReference",
    "MissingReferenceCodec",
    "ReferenceCodec",
    "ReferenceRegistry",
    "ReferenceValue",
    "encode_scalar",
]
