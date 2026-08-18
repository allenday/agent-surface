from dataclasses import FrozenInstanceError

import pytest
from pydantic import BaseModel, Field

from agent_surface import App
from agent_surface.actions import ActionCompiler, ActionDefinitionError, action


class InspectInput(BaseModel):
    ref: str
    detail: str = "summary"


class InspectResult(BaseModel):
    status: str


class DeleteInput(BaseModel):
    ref: str
    confirm: bool


def app_with_operations() -> App:
    app = App("inventory")

    @app.operation("resource.inspect", summary="Inspect a resource", read_only=True)
    def inspect(request: InspectInput) -> InspectResult:
        return InspectResult(status=request.ref)

    @app.operation("resource.delete", summary="Delete a resource", destructive=True)
    def delete(request: DeleteInput) -> InspectResult:
        return InspectResult(status=request.ref)

    return app


def test_compiles_registered_operations_and_pydantic_fields_deterministically() -> None:
    compiler = ActionCompiler(app_with_operations().operations)

    candidates = compiler.compile_operations()

    assert [item.operation for item in candidates] == ["resource.delete", "resource.inspect"]
    assert [slot.name for slot in candidates[0].slots] == ["ref", "confirm"]
    assert candidates[0].slots[0].required is True
    assert candidates[1].slots[1].required is False
    assert candidates[1].slots[1].default == "summary"
    with pytest.raises(FrozenInstanceError):
        candidates[0].operation = "changed"


class BaseActions:
    @action(operation="resource.inspect", rel="inspect-resource")
    def inspect(self, ref: str, detail: str = "summary") -> None:
        raise AssertionError("compilation must not execute decorated methods")


class ResourceActions(BaseActions):
    @property
    def dangerous(self) -> str:
        raise AssertionError("compilation must not evaluate descriptors")

    def ordinary(self, ref: str) -> None:
        raise AssertionError("undecorated methods are not candidates")


def test_compiles_only_decorated_methods_across_mro_without_descriptor_access() -> None:
    instance = ResourceActions()
    compiler = ActionCompiler(app_with_operations().operations)

    candidates = compiler.compile_object(instance)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.operation == "resource.inspect"
    assert candidate.rel == "inspect-resource"
    assert candidate.context is instance
    assert [slot.name for slot in candidate.slots] == ["ref", "detail"]
    assert candidate.slots[0].annotation is str
    assert candidate.slots[1].default == "summary"


def test_class_dictionary_scan_does_not_touch_hostile_ordinary_attributes() -> None:
    class Tripwire:
        def __getattribute__(self, name: str):
            if name == "__agent_surface_action__":
                raise AssertionError("ordinary class attributes must remain untouched")
            return super().__getattribute__(name)

    class WithTripwire(BaseActions):
        ordinary_value = Tripwire()

    candidates = ActionCompiler(app_with_operations().operations).compile_object(WithTripwire())

    assert len(candidates) == 1


def test_undecorated_subclass_override_suppresses_decorated_base_method() -> None:
    class Override(BaseActions):
        def inspect(self, ref: str) -> None:
            pass

    candidates = ActionCompiler(app_with_operations().operations).compile_object(Override())

    assert candidates == ()


def test_pydantic_default_factory_is_preserved_without_execution() -> None:
    calls = 0

    def generate_ref() -> str:
        nonlocal calls
        calls += 1
        return "generated-ref"

    class FactoryInput(BaseModel):
        ref: str = Field(default_factory=generate_ref)

    app = App("factory")

    @app.operation("resource.factory")
    def factory(request: FactoryInput) -> InspectResult:
        return InspectResult(status=request.ref)

    candidate = ActionCompiler(app.operations).compile_operations()[0]

    assert candidate.slots[0].required is False
    assert calls == 0


@pytest.mark.parametrize("case", ["variadic", "unannotated", "unknown"])
def test_invalid_decorated_signatures_fail_with_stable_errors(case: str) -> None:
    if case == "variadic":

        class Invalid:
            @action(operation="resource.inspect")
            def candidate(self, *refs: str) -> None:
                pass

    elif case == "unannotated":

        class Invalid:
            @action(operation="resource.inspect")
            def candidate(self, ref) -> None:  # type: ignore[no-untyped-def]
                pass

    else:

        class Invalid:
            @action(operation="resource.missing")
            def candidate(self, ref: str) -> None:
                pass

    with pytest.raises(ActionDefinitionError) as raised:
        ActionCompiler(app_with_operations().operations).compile_object(Invalid())

    assert raised.value.code in {"invalid_action_signature", "unknown_action_operation"}
