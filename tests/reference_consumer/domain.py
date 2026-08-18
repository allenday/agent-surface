"""Consumer-owned domain models and behavior."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResourceRef(DomainModel):
    value: str = Field(min_length=1, max_length=128)


class LookupRequest(DomainModel):
    ref: ResourceRef


class ResourceRecord(DomainModel):
    ref: ResourceRef
    label: str
    revision: int = Field(ge=1)


class ListRequest(DomainModel):
    cursor: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class ResourcePage(DomainModel):
    items: tuple[ResourceRecord, ...]
    total: int = Field(ge=0)
    returned: int = Field(ge=0)
    truncated: bool
    next_cursor: str | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> "ResourcePage":
        if self.returned != len(self.items):
            raise ValueError("returned must equal the number of items")
        if self.total < self.returned:
            raise ValueError("total must be greater than or equal to returned")
        if self.truncated != (self.next_cursor is not None):
            raise ValueError("truncated pages require exactly one next cursor")
        return self


class MutationRequest(DomainModel):
    ref: ResourceRef
    confirm: bool = False
    access_token: str = Field(min_length=1, repr=False, json_schema_extra={"sensitive": True})


class MutationResult(DomainModel):
    ref: ResourceRef
    revision: int = Field(ge=1)
    changed: bool


class ResourceNotFound(Exception):
    """The requested resource does not exist."""


class ConfirmationRequired(Exception):
    """A destructive operation was not explicitly confirmed."""


class Catalog:
    def __init__(self, records: tuple[ResourceRecord, ...]) -> None:
        self._records = {record.ref.value: record for record in records}

    @classmethod
    def example(cls) -> "Catalog":
        return cls(
            (
                ResourceRecord(ref=ResourceRef(value="resource-a"), label="Alpha", revision=1),
                ResourceRecord(ref=ResourceRef(value="resource-b"), label="Beta", revision=1),
            )
        )

    def lookup(self, request: LookupRequest) -> ResourceRecord:
        try:
            return self._records[request.ref.value]
        except KeyError as error:
            raise ResourceNotFound(request.ref.value) from error

    async def list_resources(self, request: ListRequest) -> ResourcePage:
        ordered = sorted(self._records.values(), key=lambda item: item.ref.value)
        start = 0
        if request.cursor is not None:
            start = next(
                (
                    index + 1
                    for index, item in enumerate(ordered)
                    if item.ref.value == request.cursor
                ),
                len(ordered),
            )
        items = tuple(ordered[start : start + request.limit])
        has_more = start + len(items) < len(ordered)
        return ResourcePage(
            items=items,
            total=len(ordered),
            returned=len(items),
            truncated=has_more,
            next_cursor=items[-1].ref.value if has_more and items else None,
        )

    def mutate(self, request: MutationRequest) -> MutationResult:
        if not request.confirm:
            raise ConfirmationRequired(request.ref.value)
        record = self.lookup(LookupRequest(ref=request.ref))
        updated = record.model_copy(update={"revision": record.revision + 1})
        self._records[request.ref.value] = updated
        return MutationResult(ref=updated.ref, revision=updated.revision, changed=True)
