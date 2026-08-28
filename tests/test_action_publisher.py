from dataclasses import dataclass, replace
from typing import Annotated, Literal

import pytest
from pydantic import BaseModel, Field

from agent_surface import App
from agent_surface.actions import (
    ActionCandidate,
    ActionCompiler,
    ActionPublisher,
    ActionSlotPlan,
    AllowActions,
    DenyAllActions,
)
from agent_surface.references import MissingReferenceCodec, ReferenceRegistry, ReferenceValue


def candidate(
    *slots: ActionSlotPlan,
    context: object | None = None,
    operation: str = "resource.inspect",
) -> ActionCandidate:
    return ActionCandidate(
        operation=operation,
        rel="inspect-resource",
        description="Inspect a resource",
        slots=slots,
        source="test",
        context=context,
    )


def test_publication_requires_policy_and_deny_all_emits_nothing() -> None:
    references = ReferenceRegistry()

    with pytest.raises(TypeError):
        ActionPublisher(references=references)  # type: ignore[call-arg]

    publisher = ActionPublisher(references=references, policy=DenyAllActions())
    assert publisher.publish((candidate(),)) == ()


def test_allow_policy_filters_operations() -> None:
    publisher = ActionPublisher(
        references=ReferenceRegistry(),
        policy=AllowActions(frozenset({"resource.inspect"})),
    )

    actions = publisher.publish(
        (
            candidate(),
            candidate(operation="resource.delete"),
        )
    )

    assert [item.operation for item in actions] == ["resource.inspect"]


class Context:
    def __init__(self) -> None:
        self.ref = "from-context"
        self.other_ref = "must-not-bind-by-type"

    @property
    def dangerous(self) -> str:
        raise AssertionError("publisher must not evaluate descriptors")


def test_binding_precedence_is_explicit_then_exact_name_then_default() -> None:
    plan = candidate(
        ActionSlotPlan(name="ref", annotation=str, required=True),
        ActionSlotPlan(name="count", annotation=int, required=False, default=2),
        context=Context(),
    )
    publisher = ActionPublisher(
        references=ReferenceRegistry(),
        policy=AllowActions(frozenset({"resource.inspect"})),
    )

    explicit = publisher.publish((plan,), values={"ref": "explicit"})[0]
    contextual = publisher.publish((plan,))[0]

    assert explicit.command == (
        "resource",
        "inspect",
        "--ref",
        "explicit",
        "--count",
        "2",
    )
    assert contextual.command is not None
    assert contextual.command[3] == "from-context"
    assert contextual.bound == {"ref": "from-context", "count": 2}


def test_root_slots_precede_the_operation_path() -> None:
    plan = candidate(
        ActionSlotPlan(name="registry", annotation=str, required=True, root=True),
        ActionSlotPlan(name="host", annotation=str, required=True),
    )
    publisher = ActionPublisher(
        references=ReferenceRegistry(),
        policy=AllowActions(frozenset({"resource.inspect"})),
    )

    published = publisher.publish((plan,), values={"registry": "local", "host": "node-1"})[0]

    assert published.command == (
        "--registry",
        "local",
        "resource",
        "inspect",
        "--host",
        "node-1",
    )


def test_dependent_pydantic_default_factory_runs_after_prior_slots_resolve() -> None:
    class FactoryInput(BaseModel):
        prefix: str
        ref: str = Field(default_factory=lambda data: f"{data['prefix']}-resource")

    class FactoryResult(BaseModel):
        status: str

    app = App("factory")

    @app.operation("resource.factory")
    def factory(request: FactoryInput) -> FactoryResult:
        return FactoryResult(status=request.ref)

    candidates = ActionCompiler(app.operations).compile_operations()
    publisher = ActionPublisher(
        references=ReferenceRegistry(),
        policy=AllowActions(frozenset({"resource.factory"})),
    )

    resolved = publisher.publish(candidates, values={"prefix": "custom"})[0]
    unresolved = publisher.publish(candidates)[0]

    assert resolved.command == (
        "resource",
        "factory",
        "--prefix",
        "custom",
        "--ref",
        "custom-resource",
    )
    assert unresolved.command is None
    assert unresolved.command_template[-1] == "{ref}"  # type: ignore[index]


def test_same_type_wrong_name_stays_unbound_and_does_not_scan_properties() -> None:
    plan = candidate(
        ActionSlotPlan(name="target", annotation=str, required=True),
        context=Context(),
    )
    publisher = ActionPublisher(
        references=ReferenceRegistry(),
        policy=AllowActions(frozenset({"resource.inspect"})),
    )

    published = publisher.publish((plan,))[0]

    assert published.command is None
    assert published.command_template == (
        "resource",
        "inspect",
        "--target",
        "{target}",
    )
    assert published.slots["target"]["required"] is True


@dataclass(frozen=True)
class Resource:
    key: str
    title: str


class ResourceCodec:
    kind = "resource"
    python_type = Resource

    def encode(self, value: Resource) -> str:
        return value.key

    def decode(self, token: str) -> Resource:
        return Resource(key=token, title=token)

    def display(self, value: Resource) -> str:
        return value.title


def test_custom_reference_uses_codec_id_and_structured_display_binding() -> None:
    references = ReferenceRegistry()
    references.register(ResourceCodec())
    publisher = ActionPublisher(
        references=references,
        policy=AllowActions(frozenset({"resource.inspect"})),
    )
    resource = Resource(key="resource-017", title="Production database")

    published = publisher.publish(
        (candidate(ActionSlotPlan(name="ref", annotation=Resource, required=True)),),
        values={"ref": resource},
    )[0]

    assert published.command == ("resource", "inspect", "--ref", "resource-017")
    assert published.bound["ref"] == ReferenceValue(
        kind="resource",
        id="resource-017",
        label="Production database",
    )


def test_bound_custom_object_without_codec_fails_instead_of_stringifying() -> None:
    publisher = ActionPublisher(
        references=ReferenceRegistry(),
        policy=AllowActions(frozenset({"resource.inspect"})),
    )

    with pytest.raises(MissingReferenceCodec):
        publisher.publish(
            (candidate(ActionSlotPlan(name="ref", annotation=Resource, required=True)),),
            values={"ref": Resource(key="one", title="One")},
        )


@pytest.mark.parametrize(
    "annotation",
    [
        Resource | None,
        Annotated[Resource, "reference"],
        Literal["known-resource"],
        list[Resource],
        tuple[Resource, ...],
        dict[str, Resource],
    ],
)
def test_structured_annotation_rejects_unrelated_codec_backed_object(
    annotation: object,
) -> None:
    @dataclass(frozen=True)
    class Other:
        key: str

    class OtherCodec:
        kind = "other"
        python_type = Other

        def encode(self, value: Other) -> str:
            return value.key

        def decode(self, token: str) -> Other:
            return Other(key=token)

        def display(self, value: Other) -> str:
            return value.key

    references = ReferenceRegistry()
    references.register(OtherCodec())
    publisher = ActionPublisher(
        references=references,
        policy=AllowActions(frozenset({"resource.inspect"})),
    )

    published = publisher.publish(
        (candidate(ActionSlotPlan(name="ref", annotation=annotation, required=True)),),
        values={"ref": Other(key="wrong-type")},
    )[0]

    assert published.command is None
    assert published.command_template[-1] == "{ref}"  # type: ignore[index]


def test_unbound_slot_retains_one_paginated_source_without_expansion() -> None:
    slot = ActionSlotPlan(name="ref", annotation=Resource, required=True)
    slot = replace(
        slot,
        source={
            "command": ["resource", "list", "--cursor", "page-2", "--limit", "20"]
        },
    )
    publisher = ActionPublisher(
        references=ReferenceRegistry(),
        policy=AllowActions(frozenset({"resource.inspect"})),
    )

    published = publisher.publish((candidate(slot),))[0]

    assert published.command_template[-1] == "{ref}"  # type: ignore[index]
    assert published.slots["ref"]["source"] == slot.source
    assert len(published.slots) == 1
