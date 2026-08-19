"""A complete HATEOAS bookstore projected through sibling Click and MCP adapters."""

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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


class GetHoldRequest(DomainModel):
    hold: str


class DeleteHoldRequest(DomainModel):
    hold: str
    confirm: bool = False


class Hold(DomainModel):
    id: str
    book: BookRef
    status: Literal["active", "cancelled"]


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
    def __init__(self, db_path: str | Path = ":memory:") -> None:
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
        if db_path != ":memory:":
            Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._database = sqlite3.connect(str(db_path))
        self._database.row_factory = sqlite3.Row
        with self._database:
            self._database.execute(
                """
                CREATE TABLE IF NOT EXISTS holds (
                    id TEXT PRIMARY KEY,
                    book TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('active', 'cancelled'))
                )
                """
            )

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
        try:
            with self._database:
                self._database.execute(
                    "INSERT INTO holds (id, book, status) VALUES (?, ?, ?)",
                    (hold.id, hold.book.value, hold.status),
                )
        except sqlite3.IntegrityError as error:
            raise OperationError(
                "hold_exists",
                "A hold already exists for this book",
                details=({"hold": hold.id},),
                fix="Read, cancel, or delete the existing hold.",
            ) from error
        return hold

    def get_hold(self, request: GetHoldRequest) -> Hold:
        row = self._database.execute(
            "SELECT id, book, status FROM holds WHERE id = ?",
            (request.hold,),
        ).fetchone()
        if row is None:
            raise OperationError(
                "hold_not_found",
                "Hold was not found",
                details=({"hold": request.hold},),
                fix="Choose a hold returned by holds.create.",
            )
        return Hold(
            id=row["id"],
            book=BookRef(value=row["book"]),
            status=row["status"],
        )

    def cancel_hold(self, request: CancelHoldRequest) -> Hold:
        hold = self.get_hold(GetHoldRequest(hold=request.hold))
        cancelled = hold.model_copy(update={"status": "cancelled"})
        with self._database:
            self._database.execute(
                "UPDATE holds SET status = ? WHERE id = ?",
                (cancelled.status, cancelled.id),
            )
        return cancelled

    def delete_hold(self, request: DeleteHoldRequest) -> Hold:
        hold = self.get_hold(GetHoldRequest(hold=request.hold))
        with self._database:
            self._database.execute("DELETE FROM holds WHERE id = ?", (hold.id,))
        return hold


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
                Action(
                    rel="get-hold",
                    operation="holds.get",
                    command_template=(root, "holds", "get", "--hold", "{hold}"),
                ),
                Action(
                    rel="cancel-hold",
                    operation="holds.cancel",
                    command_template=(root, "holds", "cancel", "--hold", "{hold}", "--confirm"),
                ),
                Action(
                    rel="delete-hold",
                    operation="holds.delete",
                    command_template=(root, "holds", "delete", "--hold", "{hold}", "--confirm"),
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
                        rel="get",
                        operation="holds.get",
                        command=(
                            self._root,
                            "holds",
                            "get",
                            "--hold",
                            result.id,
                        ),
                        bound={"hold": result.id},
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
                    Action(
                        rel="delete",
                        operation="holds.delete",
                        command=(
                            self._root,
                            "holds",
                            "delete",
                            "--hold",
                            result.id,
                            "--confirm",
                        ),
                        bound={"hold": result.id, "confirm": True},
                    ),
                )
            )
        elif operation == "holds.get" and isinstance(result, Hold):
            if result.status == "active":
                actions.append(
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
                    )
                )
            actions.append(
                Action(
                    rel="delete",
                    operation="holds.delete",
                    command=(
                        self._root,
                        "holds",
                        "delete",
                        "--hold",
                        result.id,
                        "--confirm",
                    ),
                    bound={"hold": result.id, "confirm": True},
                )
            )
        elif operation == "holds.cancel" and isinstance(result, Hold):
            actions.extend(
                (
                    Action(
                        rel="get",
                        operation="holds.get",
                        command=(self._root, "holds", "get", "--hold", result.id),
                        bound={"hold": result.id},
                    ),
                    Action(
                        rel="delete",
                        operation="holds.delete",
                        command=(
                            self._root,
                            "holds",
                            "delete",
                            "--hold",
                            result.id,
                            "--confirm",
                        ),
                        bound={"hold": result.id, "confirm": True},
                    ),
                )
            )
        elif operation == "holds.delete" and isinstance(result, Hold):
            actions.append(
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


def build_surface(db_path: str | Path = ":memory:") -> BookstoreSurface:
    store = Bookstore(db_path)
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

    @app.operation("holds.get", summary="Read one hold", read_only=True, idempotent=True)
    def get_hold(request: GetHoldRequest) -> Hold:
        return store.get_hold(request)

    @app.operation("holds.cancel", summary="Cancel one hold", destructive=True, idempotent=True)
    def cancel_hold(request: CancelHoldRequest) -> Hold:
        return store.cancel_hold(request)

    @app.operation("holds.delete", summary="Delete one hold", destructive=True)
    def delete_hold(request: DeleteHoldRequest) -> Hold:
        return store.delete_hold(request)

    references = ReferenceRegistry()
    references.register(BookRefCodec())
    return BookstoreSurface(
        app=app,
        store=store,
        references=references,
        actions=BookstoreActions(),
    )


def configured_db_path() -> Path:
    configured = os.environ.get("AGENT_SURFACE_BOOKSTORE_DB")
    if configured:
        return Path(configured).expanduser()
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "agent-surface" / "bookstore.sqlite3"


def main() -> None:
    build_surface(configured_db_path()).cli()(prog_name="./examples/bookstore")


if __name__ == "__main__":
    main()
