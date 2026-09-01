import pytest
from pydantic import BaseModel

from agent_surface.app import App
from agent_surface.operations import (
    DuplicateOperationError,
    OperationError,
    OperationInputError,
    OperationOutcome,
    OperationOutputError,
    UnknownOperationError,
)


class AddInput(BaseModel):
    left: int
    right: int


class AddResult(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_registers_and_invokes_sync_handler() -> None:
    app = App("calculator")

    @app.operation("math.add", summary="Add two integers")
    def add(request: AddInput) -> AddResult:
        return AddResult(value=request.left + request.right)

    result = await app.invoke("math.add", {"left": 2, "right": 3})

    assert result == AddResult(value=5)
    assert app.operations.describe("math.add").summary == "Add two integers"


@pytest.mark.asyncio
async def test_invokes_async_handler_and_validates_mapping_output() -> None:
    app = App("calculator")

    @app.operation("math.double")
    async def double(request: AddResult) -> AddResult:
        return {"value": request.value * 2}  # type: ignore[return-value]

    result = await app.invoke("math.double", {"value": 4})

    assert result == AddResult(value=8)


def test_duplicate_operation_names_fail_registration() -> None:
    app = App("calculator")

    @app.operation("math.add")
    def first(request: AddInput) -> AddResult:
        return AddResult(value=0)

    with pytest.raises(DuplicateOperationError, match="math.add"):

        @app.operation("math.add")
        def second(request: AddInput) -> AddResult:
            return AddResult(value=1)


@pytest.mark.asyncio
async def test_invalid_input_has_stable_error_code() -> None:
    app = App("calculator")

    @app.operation("math.add")
    def add(request: AddInput) -> AddResult:
        return AddResult(value=request.left + request.right)

    with pytest.raises(OperationInputError) as caught:
        await app.invoke("math.add", {"left": "not-an-int", "right": 1})

    assert caught.value.code == "invalid_input"
    assert caught.value.details


@pytest.mark.asyncio
async def test_invalid_output_has_stable_error_code() -> None:
    app = App("calculator")

    @app.operation("math.bad")
    def bad(request: AddResult) -> AddResult:
        return {"wrong": request.value}  # type: ignore[return-value]

    with pytest.raises(OperationOutputError) as caught:
        await app.invoke("math.bad", {"value": 4})

    assert caught.value.code == "invalid_output"


@pytest.mark.asyncio
async def test_domain_errors_pass_through_unchanged() -> None:
    app = App("calculator")

    @app.operation("math.missing")
    def missing(request: AddResult) -> AddResult:
        raise OperationError("not_found", "Value was not found", fix="Choose another value.")

    with pytest.raises(OperationError) as caught:
        await app.invoke("math.missing", {"value": 4})

    assert caught.value.code == "not_found"
    assert caught.value.fix == "Choose another value."


@pytest.mark.asyncio
async def test_successful_outcome_preserves_result_and_process_exit_code() -> None:
    app = App("calculator")

    @app.operation("math.status")
    def status(request: AddResult) -> OperationOutcome[AddResult]:
        return OperationOutcome(AddResult(value=request.value), exit_code=1)

    definition = app.operations.describe("math.status")
    request = app.operations.validate(definition, {"value": 4})
    invocation = await app.operations._invoke_request_with_outcome(definition, request)

    assert invocation.result == AddResult(value=4)
    assert invocation.exit_code == 1
    assert await app.invoke("math.status", {"value": 4}) == AddResult(value=4)


def test_successful_outcome_rejects_unsafe_exit_codes() -> None:
    with pytest.raises(ValueError, match="0 through 125"):
        OperationOutcome(AddResult(value=4), exit_code=126)


@pytest.mark.asyncio
async def test_declared_outcome_must_be_returned_by_the_handler() -> None:
    app = App("calculator")

    @app.operation("math.status")
    def status(request: AddResult) -> OperationOutcome[AddResult]:
        return request  # type: ignore[return-value]

    with pytest.raises(OperationError, match="must return an OperationOutcome") as caught:
        await app.invoke("math.status", {"value": 4})

    assert caught.value.code == "invalid_outcome"


@pytest.mark.asyncio
async def test_unknown_operation_is_explicit() -> None:
    app = App("calculator")

    with pytest.raises(UnknownOperationError, match="missing"):
        await app.invoke("missing", {})


def test_registration_requires_typed_request_and_result_models() -> None:
    app = App("calculator")

    with pytest.raises(TypeError, match="Pydantic"):

        @app.operation("untyped")
        def untyped(request):  # type: ignore[no-untyped-def]
            return request
