"""A complete HATEOAS bookstore projected through sibling Click and MCP adapters."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_surface import (
    Action,
    ActionCatalog,
    ActionCollection,
    App,
    OperationError,
    OutputBudget,
    ReferenceRegistry,
)
from agent_surface.adapters.click import build_click_group


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BookRef(DomainModel):
    value: str = Field(min_length=1, max_length=128)


class Book(DomainModel):
    ref: BookRef
    title: str
    author: str


class SearchRequest(DomainModel):
    query: str = Field(min_length=1, description="Title or author search text")
    cursor: str | None = None
    limit: int = Field(default=2, ge=1, le=20)


class SearchPage(DomainModel):
    query: str
    items: tuple[Book, ...]
    total: int = Field(ge=0)
    returned: int = Field(ge=0)
    truncated: bool
    next_cursor: str | None = None

    @model_validator(mode="after")
    def validate_page(self) -> "SearchPage":
        if self.returned != len(self.items):
            raise ValueError("returned must equal the number of books")
        if self.truncated != (self.next_cursor is not None):
            raise ValueError("truncated pages require exactly one cursor")
        return self


class InspectRequest(DomainModel):
    book: BookRef


class BookDetail(Book):
    available: bool


class CreateHoldRequest(DomainModel):
    book: BookRef
    confirm: bool = False


class CancelHoldRequest(DomainModel):
    hold: str
    confirm: bool = False


class Hold(DomainModel):
    id: str
    book: BookRef
    status: str


class BookRefCodec:
    kind = "book"
    python_type = BookRef

    def encode(self, value: BookRef) -> str:
        return value.value

    def decode(self, token: str) -> BookRef:
        return BookRef(value=token)

    def display(self, value: BookRef) -> str:
        return value.value


class Bookstore:
    def __init__(self) -> None:
        books = (
            Book(ref=BookRef(value="book_dune"), title="Dune", author="Frank Herbert"),
            Book(
                ref=BookRef(value="book_dune_messiah"),
                title="Dune Messiah",
                author="Frank Herbert",
            ),
            Book(
                ref=BookRef(value="book_children_of_dune"),
                title="Children of Dune",
                author="Frank Herbert",
            ),
            Book(ref=BookRef(value="book_foundation"), title="Foundation", author="Isaac Asimov"),
        )
        self._books = {book.ref.value: book for book in books}
        self._holds: dict[str, Hold] = {}

    async def search(self, request: SearchRequest) -> SearchPage:
        matches = tuple(
            book
            for book in self._books.values()
            if request.query.casefold() in f"{book.title} {book.author}".casefold()
        )
        start = 0
        if request.cursor is not None:
            start = next(
                (
                    index + 1
                    for index, book in enumerate(matches)
                    if book.ref.value == request.cursor
                ),
                len(matches),
            )
        items = matches[start : start + request.limit]
        has_more = start + len(items) < len(matches)
        return SearchPage(
            query=request.query,
            items=items,
            total=len(matches),
            returned=len(items),
            truncated=has_more,
            next_cursor=items[-1].ref.value if has_more and items else None,
        )

    def inspect(self, request: InspectRequest) -> BookDetail:
        try:
            book = self._books[request.book.value]
        except KeyError as error:
            raise OperationError(
                "book_not_found",
                "Book was not found",
                details=({"book": request.book.value},),
                fix="Choose a book reference returned by books.search.",
            ) from error
        return BookDetail(**book.model_dump(), available=True)

    def create_hold(self, request: CreateHoldRequest) -> Hold:
        self.inspect(InspectRequest(book=request.book))
        hold = Hold(id=f"hold_{request.book.value}", book=request.book, status="active")
        self._holds[hold.id] = hold
        return hold

    def cancel_hold(self, request: CancelHoldRequest) -> Hold:
        try:
            hold = self._holds[request.hold]
        except KeyError as error:
            raise OperationError(
                "hold_not_found",
                "Hold was not found",
                fix="Choose a hold returned by holds.create.",
            ) from error
        cancelled = hold.model_copy(update={"status": "cancelled"})
        self._holds[hold.id] = cancelled
        return cancelled


class BookstoreActions:
    def __init__(self, root: str = "./examples/bookstore") -> None:
        self._root = root
        self._catalog = ActionCatalog(
            (
                Action(
                    rel="search",
                    operation="books.search",
                    command_template=(root, "books", "search", "--query", "{query}"),
                ),
                Action(
                    rel="inspect",
                    operation="books.inspect",
                    command_template=(root, "books", "inspect", "--book", "{book}"),
                ),
                Action(
                    rel="reserve",
                    operation="holds.create",
                    command_template=(root, "holds", "create", "--book", "{book}", "--confirm"),
                ),
            ),
            discovery_command=(root, "actions", "list"),
        )

    def actions_for(
        self,
        *,
        operation: str,
        result: object | None = None,
        error: OperationError | None = None,
    ) -> ActionCollection:
        del error
        actions: list[Action] = []
        if operation == "books.search" and isinstance(result, SearchPage):
            if result.items:
                actions.append(
                    Action(
                        rel="inspect",
                        description="Inspect the first returned book",
                        operation="books.inspect",
                        command=(
                            self._root,
                            "books",
                            "inspect",
                            "--book",
                            result.items[0].ref.value,
                        ),
                        bound={"book": result.items[0].ref.value},
                    )
                )
            if result.next_cursor is not None:
                actions.append(
                    Action(
                        rel="next-page",
                        description="Continue this search",
                        operation="books.search",
                        command=(
                            self._root,
                            "books",
                            "search",
                            "--query",
                            result.query,
                            "--cursor",
                            result.next_cursor,
                            "--limit",
                            "2",
                        ),
                        bound={
                            "query": result.query,
                            "cursor": result.next_cursor,
                            "limit": 2,
                        },
                    )
                )
        elif operation == "books.inspect" and isinstance(result, BookDetail):
            actions.append(
                Action(
                    rel="reserve",
                    description="Reserve this available book",
                    operation="holds.create",
                    command=(
                        self._root,
                        "holds",
                        "create",
                        "--book",
                        result.ref.value,
                        "--confirm",
                    ),
                    bound={"book": result.ref.value, "confirm": True},
                )
            )
        elif operation == "holds.create" and isinstance(result, Hold):
            actions.extend(
                (
                    Action(
                        rel="inspect-book",
                        operation="books.inspect",
                        command=(
                            self._root,
                            "books",
                            "inspect",
                            "--book",
                            result.book.value,
                        ),
                        bound={"book": result.book.value},
                    ),
                    Action(
                        rel="cancel",
                        operation="holds.cancel",
                        command=(
                            self._root,
                            "holds",
                            "cancel",
                            "--hold",
                            result.id,
                            "--confirm",
                        ),
                        bound={"hold": result.id, "confirm": True},
                    ),
                )
            )
        return ActionCollection(
            items=tuple(actions),
            total=len(actions),
            returned=len(actions),
        )

    def list_actions(
        self,
        *,
        cursor: str | None = None,
        budget: OutputBudget | None = None,
    ) -> ActionCollection:
        return self._catalog.page(cursor=cursor, budget=budget)

    def explain(self, operation: str) -> Action | None:
        return next(
            (item for item in self._catalog.page().items if item.operation == operation),
            None,
        )


@dataclass(frozen=True)
class BookstoreSurface:
    app: App
    store: Bookstore
    references: ReferenceRegistry
    actions: BookstoreActions

    def cli(self):
        return build_click_group(
            self.app,
            references=self.references,
            action_provider=self.actions,
        )

    def mcp(self):
        from agent_surface.adapters.mcp import MCPAdapter

        return MCPAdapter(
            self.app,
            references=self.references,
            action_provider=self.actions,
        )


def build_surface() -> BookstoreSurface:
    store = Bookstore()
    app = App("bookstore")

    @app.operation("books.search", summary="Search the bookstore", read_only=True, open_world=True)
    async def search(request: SearchRequest) -> SearchPage:
        return await store.search(request)

    @app.operation("books.inspect", summary="Inspect one book", read_only=True, idempotent=True)
    def inspect(request: InspectRequest) -> BookDetail:
        return store.inspect(request)

    @app.operation("holds.create", summary="Reserve one book", destructive=True)
    def create_hold(request: CreateHoldRequest) -> Hold:
        return store.create_hold(request)

    @app.operation("holds.cancel", summary="Cancel one hold", destructive=True, idempotent=True)
    def cancel_hold(request: CancelHoldRequest) -> Hold:
        return store.cancel_hold(request)

    references = ReferenceRegistry()
    references.register(BookRefCodec())
    return BookstoreSurface(
        app=app,
        store=store,
        references=references,
        actions=BookstoreActions(),
    )


def main() -> None:
    build_surface().cli()(prog_name="./examples/bookstore")


if __name__ == "__main__":
    main()
