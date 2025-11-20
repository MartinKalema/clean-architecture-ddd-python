from dependency_injector import containers, providers
from src.infrastructure.repositories.sql_book_repository import SQLBookRepository
from src.presentation.api.controllers.book_controller import BookController
from src.infrastructure.external.database import SessionLocal

from src.application.use_cases.add_book import AddBook
from src.application.use_cases.list_books import ListBooks
from src.application.use_cases.borrow_book import BorrowBook

class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=[
        "src.presentation.api.routes.book_routes",
        "src.presentation.cli.main"
    ])

    db_session = providers.Factory(SessionLocal)

    book_repository = providers.Factory(
        SQLBookRepository,
        session=db_session
    )

    # Use Cases
    add_book_use_case = providers.Factory(
        AddBook,
        repository=book_repository
    )

    list_books_use_case = providers.Factory(
        ListBooks,
        repository=book_repository
    )

    borrow_book_use_case = providers.Factory(
        BorrowBook,
        repository=book_repository
    )

    book_controller = providers.Factory(
        BookController,
        repository=book_repository
    )
