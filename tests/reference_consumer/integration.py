"""The sole boundary between the consumer domain and agent-surface."""

from agent_surface import App, OperationError
from tests.reference_consumer.domain import (
    Catalog,
    ConfirmationRequired,
    ListRequest,
    LookupRequest,
    MutationRequest,
    MutationResult,
    ResourceNotFound,
    ResourcePage,
    ResourceRecord,
)


def build_app(service: Catalog | None = None) -> tuple[App, Catalog]:
    catalog = service or Catalog.example()
    app = App("reference-consumer")

    @app.operation(
        "resource.lookup",
        summary="Look up one resource",
        read_only=True,
        idempotent=True,
    )
    def lookup(request: LookupRequest) -> ResourceRecord:
        try:
            return catalog.lookup(request)
        except ResourceNotFound as error:
            ref = str(error)
            raise OperationError(
                "resource_not_found",
                "Resource was not found",
                details=({"ref": ref},),
                fix="Choose a reference returned by resource.list",
            ) from error

    @app.operation(
        "resource.list",
        summary="List a bounded page of resources",
        read_only=True,
        idempotent=True,
        open_world=True,
    )
    async def list_resources(request: ListRequest) -> ResourcePage:
        return await catalog.list_resources(request)

    @app.operation(
        "resource.mutate",
        summary="Apply a confirmed resource mutation",
        destructive=True,
    )
    def mutate(request: MutationRequest) -> MutationResult:
        try:
            return catalog.mutate(request)
        except ConfirmationRequired as error:
            raise OperationError(
                "confirmation_required",
                "Resource mutation requires explicit confirmation",
                details=({"ref": str(error)},),
                fix="Set confirm=true after reviewing the target",
            ) from error
        except ResourceNotFound as error:
            raise OperationError(
                "resource_not_found",
                "Resource was not found",
                details=({"ref": str(error)},),
                fix="Choose a reference returned by resource.list",
            ) from error

    return app, catalog
