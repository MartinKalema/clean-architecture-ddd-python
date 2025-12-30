"""
Integration tests for CQRS Command Handlers.
"""
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.command_handlers import (
    AddBookCommand,
    AddBookHandler,
    BorrowBookCommand,
    BorrowBookHandler,
)
from src.domain.catalog import BookAlreadyBorrowedException
from src.infrastructure.adapters.repositories.unit_of_work import (
    UnitOfWork,
)


@pytest.mark.asyncio
async def test_add_book_use_case(test_db):
    """Test AddBookHandler creates a book."""
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = UnitOfWork(session_factory)
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
    uow = UnitOfWork(session_factory)
    mock_logger = MagicMock()
    
    # Mock Patron Service
    from unittest.mock import AsyncMock
    mock_patron_service = MagicMock()
    mock_borrower = MagicMock()
    mock_borrower.can_borrow = True
    mock_patron_service.get_borrower_by_email = AsyncMock(return_value=mock_borrower)
    
    add_handler = AddBookHandler(uow, logger=mock_logger)
    borrow_handler = BorrowBookHandler(uow, patron_service=mock_patron_service, logger=mock_logger)

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
    uow = UnitOfWork(session_factory)
    mock_logger = MagicMock()
    
    # Mock Patron Service
    from unittest.mock import AsyncMock
    mock_patron_service = MagicMock()
    mock_borrower = MagicMock()
    mock_borrower.can_borrow = True
    mock_patron_service.get_borrower_by_email = AsyncMock(return_value=mock_borrower)

    add_handler = AddBookHandler(uow, logger=mock_logger)
    borrow_handler = BorrowBookHandler(uow, patron_service=mock_patron_service, logger=mock_logger)

    # Add
    add_command = AddBookCommand(title="Twice Borrowed", author="UC Tester")
    book_result = await add_handler.handle(add_command)

    # Borrow once
    await borrow_handler.handle(BorrowBookCommand(book_id=book_result.id, borrower_email="test@example.com"))

    # Borrow again - should fail
    with pytest.raises(BookAlreadyBorrowedException):
        await borrow_handler.handle(BorrowBookCommand(book_id=book_result.id, borrower_email="another@example.com"))
