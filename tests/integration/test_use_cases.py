"""
Integration tests for CQRS Command Handlers.
"""
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.application.ports import BorrowerProfile


def _patron_repository(patron=...):
    """Stub the anti-corruption borrower directory."""
    repo = AsyncMock()
    repo.find_by_email.return_value = (
        BorrowerProfile(
            patron_id="patron-uc-1",
            email="uc@example.com",
            is_eligible=True,
            membership_tier="regular",
        ) if patron is ... else patron
    )
    return repo


class _Clock:
    def now(self):
        return datetime(2026, 7, 11, tzinfo=timezone.utc)

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
    borrow_handler = BorrowBookHandler(
        uow,
        borrower_directory=_patron_repository(),
        logger=mock_logger,
        clock=_Clock(),
    )

    # Add
    add_command = AddBookCommand(title="Borrowable Book", author="UC Tester")
    book_result = await add_handler.handle(add_command)

    # Borrow
    borrow_command = BorrowBookCommand(book_id=book_result.id, borrower_email="test@example.com")
    borrowed_book = await borrow_handler.handle(borrow_command)

    assert borrowed_book.is_borrowed is False
    assert borrowed_book.status == "reserved"

    # Verify persistence
    async with uow:
        fetched_book = await uow.books.get_by_id(book_result.id)
        assert fetched_book.is_borrowed is False
        assert fetched_book.is_unavailable is True


@pytest.mark.asyncio
async def test_borrow_book_already_borrowed(test_db):
    """Test BorrowBookHandler raises exception for already borrowed book."""
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = CatalogUnitOfWork(session_factory)
    mock_logger = MagicMock()
    add_handler = AddBookHandler(uow, logger=mock_logger)
    borrow_handler = BorrowBookHandler(
        uow,
        borrower_directory=_patron_repository(),
        logger=mock_logger,
        clock=_Clock(),
    )

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
        uow,
        borrower_directory=_patron_repository(patron=None),
        logger=mock_logger,
        clock=_Clock(),
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
