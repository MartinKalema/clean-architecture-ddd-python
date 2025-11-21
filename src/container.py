from dependency_injector import containers, providers
from src.infrastructure.repositories.sql_book_repository import SQLBookRepository

from src.infrastructure.configurations.settings import load_config
from src.infrastructure.external.database import Database

from src.application.use_cases.add_book import AddBook
from src.application.use_cases.list_books import ListBooks
from src.application.use_cases.borrow_book import BorrowBook

class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=[
        "src.presentation.api.routes.book_routes",
        "src.presentation.cli.commands.add_book_command",
        "src.presentation.cli.commands.list_books_command",
        "src.presentation.cli.commands.borrow_book_command"
    ])

    config = providers.Configuration()
    config.from_dict(load_config())

    database = providers.Singleton(
        Database,
        db_url=config.database.url
    )

    session_factory = providers.Resource(
        lambda db: db.session_factory,
        db=database
    )

    book_repository = providers.Factory(
        SQLBookRepository,
        session_factory=session_factory
    )

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


