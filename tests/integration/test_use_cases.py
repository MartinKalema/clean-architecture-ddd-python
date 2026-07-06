"""
Integration tests for CQRS Command Handlers.
"""
from unittest.mock import AsyncMock, MagicMock


def _patron_repository(patron=...):
    """Stub patron read model for the borrow pre-flight check."""
    repo = AsyncMock()
    repo.find_by_email.return_value = (
        PatronReadModel(
            id="patron-uc-1", name="UC Patron", first_name="UC", last_name="Patron",
            email="uc@example.com", membership_tier="regular",
            is_suspended=False, suspended_reason=None,
            registered_at=datetime(2026, 1, 1),
        ) if patron is ... else patron
    )
    return repo

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.command_handlers import (
    AddBookCommand,
    AddBookHandler,
    BorrowBookCommand,
    BorrowBookHandler,
)
from src.domain.catalog import (BookAlreadyBorrowedException,
                                BorrowerNotEligibleException)
from src.application.query_handlers import PatronReadModel
from src.infrastructure.adapters.catalog import CatalogUnitOfWork


@pytest.mark.asyncio
async def test_add_book_use_case(test_db):
    """Test AddBookHandler creates a book."""
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = CatalogUnitOfWork(session_factory)
    mock_logger = MagicMock()
    handler = AddBookHandler(uow, logger=mock_logger)

    command = AddBookCommand(title="Use Case Book", author="UC Tester")
    result = await handler.handle(command)

    assert result.title == "Use Case Book"
    assert result.id is not None


@pytest.mark.asyncio
async def test_borrow_book_use_case(test_db):
    """Test BorrowBookHandler borrows a book."""
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = CatalogUnitOfWork(session_factory)
    mock_logger = MagicMock()
    add_handler = AddBookHandler(uow, logger=mock_logger)
    borrow_handler = BorrowBookHandler(uow, patron_query_repository=_patron_repository(), logger=mock_logger)

    # Add
    add_command = AddBookCommand(title="Borrowable Book", author="UC Tester")
    book_result = await add_handler.handle(add_command)

    # Borrow
    borrow_command = BorrowBookCommand(book_id=book_result.id, borrower_email="test@example.com")
    borrowed_book = await borrow_handler.handle(borrow_command)

    assert borrowed_book.is_borrowed is True

    # Verify persistence
    async with uow:
        fetched_book = await uow.books.get_by_id(book_result.id)
        assert fetched_book.is_borrowed is True


@pytest.mark.asyncio
async def test_borrow_book_already_borrowed(test_db):
    """Test BorrowBookHandler raises exception for already borrowed book."""
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = CatalogUnitOfWork(session_factory)
    mock_logger = MagicMock()
    add_handler = AddBookHandler(uow, logger=mock_logger)
    borrow_handler = BorrowBookHandler(uow, patron_query_repository=_patron_repository(), logger=mock_logger)

    # Add
    add_command = AddBookCommand(title="Twice Borrowed", author="UC Tester")
    book_result = await add_handler.handle(add_command)

    # Borrow once
    await borrow_handler.handle(BorrowBookCommand(book_id=book_result.id, borrower_email="test@example.com"))

    # Borrow again - should fail
    with pytest.raises(BookAlreadyBorrowedException):
        await borrow_handler.handle(BorrowBookCommand(book_id=book_result.id, borrower_email="another@example.com"))


@pytest.mark.asyncio
async def test_borrow_rejected_before_reserving_for_unknown_patron(test_db):
    """The pre-flight check rejects doomed borrows without taking the lock."""
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = CatalogUnitOfWork(session_factory)
    mock_logger = MagicMock()
    add_handler = AddBookHandler(uow, logger=mock_logger)
    borrow_handler = BorrowBookHandler(
        uow, patron_query_repository=_patron_repository(patron=None), logger=mock_logger
    )

    book = await add_handler.handle(AddBookCommand(title="Preflight Reject", author="UC Tester"))

    with pytest.raises(BorrowerNotEligibleException):
        await borrow_handler.handle(
            BorrowBookCommand(book_id=book.id, borrower_email="ghost@example.com")
        )

    # No lock was taken: the book is still available, no compensation needed
    async with uow:
        fetched = await uow.books.get_by_id(book.id)
        assert fetched.is_borrowed is False
