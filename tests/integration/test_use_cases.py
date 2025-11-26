import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from unittest.mock import MagicMock

from src.infrastructure.adapters.repositories.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.application.use_cases.add_book import AddBook
from src.application.use_cases.borrow_book import BorrowBook
from src.application.dto.book_dto import AddBookInputDto, BorrowBookInputDto
from src.domain.catalog import BookId, BookAlreadyBorrowedException


@pytest.mark.asyncio
async def test_add_book_use_case(test_db):
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = SqlAlchemyUnitOfWork(session_factory)
    mock_logger = MagicMock()
    use_case = AddBook(uow, logger=mock_logger)

    dto = AddBookInputDto(title="Use Case Book", author="UC Tester")
    result = await use_case.execute(dto)

    assert result.title == "Use Case Book"
    assert result.id is not None


@pytest.mark.asyncio
async def test_borrow_book_use_case(test_db):
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = SqlAlchemyUnitOfWork(session_factory)
    mock_logger = MagicMock()
    add_use_case = AddBook(uow, logger=mock_logger)
    borrow_use_case = BorrowBook(uow, logger=mock_logger)

    # Add
    add_dto = AddBookInputDto(title="Borrowable Book", author="UC Tester")
    book_dto = await add_use_case.execute(add_dto)

    # Borrow
    borrow_dto = BorrowBookInputDto(book_id=book_dto.id, borrower_email="test@example.com")
    borrowed_book = await borrow_use_case.execute(borrow_dto)

    assert borrowed_book.is_borrowed is True

    # Verify persistence
    async with uow:
        fetched_book = await uow.books.get_by_id(book_dto.id)
        assert fetched_book.is_borrowed is True


@pytest.mark.asyncio
async def test_borrow_book_already_borrowed(test_db):
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = SqlAlchemyUnitOfWork(session_factory)
    mock_logger = MagicMock()
    add_use_case = AddBook(uow, logger=mock_logger)
    borrow_use_case = BorrowBook(uow, logger=mock_logger)

    # Add
    add_dto = AddBookInputDto(title="Twice Borrowed", author="UC Tester")
    book_dto = await add_use_case.execute(add_dto)

    # Borrow once
    await borrow_use_case.execute(BorrowBookInputDto(book_id=book_dto.id, borrower_email="test@example.com"))

    # Borrow again - should fail
    with pytest.raises(BookAlreadyBorrowedException):
        await borrow_use_case.execute(BorrowBookInputDto(book_id=book_dto.id, borrower_email="another@example.com"))
