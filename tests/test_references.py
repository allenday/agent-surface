from dataclasses import dataclass
from enum import StrEnum

import pytest

from agent_surface.references import (
    DuplicateReferenceCodec,
    InvalidReference,
    MissingReferenceCodec,
    ReferenceRegistry,
    ReferenceValue,
    encode_scalar,
)


@dataclass(frozen=True)
class Resource:
    key: str
    title: str

    def __str__(self) -> str:
        return f"tempting:{self.title}"


class ResourceCodec:
    kind = "resource"
    python_type = Resource

    def encode(self, value: Resource) -> str:
        return value.key

    def decode(self, token: str) -> Resource:
        return Resource(key=token, title=f"Resource {token}")

    def display(self, value: Resource) -> str:
        return value.title


def test_registry_round_trips_identity_separately_from_display() -> None:
    registry = ReferenceRegistry()
    registry.register(ResourceCodec())
    resource = Resource(key="resource-017", title="Production database")

    encoded = registry.encode(resource)
    decoded = registry.decode(encoded)

    assert encoded == ReferenceValue(
        kind="resource",
        id="resource-017",
        label="Production database",
    )
    assert decoded.key == resource.key
    assert decoded.title == "Resource resource-017"
    assert encoded.id != encoded.label


def test_registry_rejects_duplicate_kind_and_python_type() -> None:
    registry = ReferenceRegistry()
    registry.register(ResourceCodec())

    with pytest.raises(DuplicateReferenceCodec) as kind:
        registry.register(ResourceCodec())
    assert kind.value.code == "duplicate_reference_codec"

    class OtherKindCodec(ResourceCodec):
        kind = "other"

    with pytest.raises(DuplicateReferenceCodec, match="Resource"):
        registry.register(OtherKindCodec())


def test_registry_rejects_invalid_decode_type_and_unstable_round_trip() -> None:
    class WrongTypeCodec(ResourceCodec):
        def decode(self, token: str) -> object:
            return object()

    wrong = ReferenceRegistry()
    wrong.register(WrongTypeCodec())
    with pytest.raises(InvalidReference) as decoded:
        wrong.decode(ReferenceValue(kind="resource", id="one"))
    assert decoded.value.code == "invalid_reference"

    class UnstableCodec(ResourceCodec):
        def encode(self, value: Resource) -> str:
            return f"x-{value.key}"

        def decode(self, token: str) -> Resource:
            return Resource(key=token, title=token)

    unstable = ReferenceRegistry()
    unstable.register(UnstableCodec())
    with pytest.raises(InvalidReference, match="round-trip"):
        unstable.encode(Resource(key="one", title="One"))


def test_custom_objects_require_codec_and_never_fall_back_to_str() -> None:
    registry = ReferenceRegistry()

    with pytest.raises(MissingReferenceCodec) as raised:
        registry.encode(Resource(key="one", title="One"))

    assert raised.value.code == "missing_reference_codec"
    assert "tempting" not in str(raised.value)


class Mode(StrEnum):
    SAFE = "safe"


@pytest.mark.parametrize(
    ("value", "token"),
    [
        ("hello world", "hello world"),
        (True, "true"),
        (False, "false"),
        (17, "17"),
        (2.5, "2.5"),
        (None, "null"),
        (Mode.SAFE, "safe"),
    ],
)
def test_scalar_tokens_are_canonical(value: object, token: str) -> None:
    assert encode_scalar(value) == token


@pytest.mark.parametrize("value", [float("inf"), float("nan"), object()])
def test_unsupported_scalars_are_rejected(value: object) -> None:
    with pytest.raises(MissingReferenceCodec):
        encode_scalar(value)


def test_scalar_subclasses_cannot_override_canonical_token_encoding() -> None:
    class EvilInt(int):
        def __str__(self) -> str:
            return "ATTACKER-TOKEN"

        def __repr__(self) -> str:
            return "ATTACKER-TOKEN"

    with pytest.raises(MissingReferenceCodec):
        encode_scalar(EvilInt(7))
