import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from src.infrastructure.adapters.repositories.sql_book_repository import SQLBookRepository
from src.domain.entities.book import Book
from src.domain.value_objects.book_value_objects import BookId, Title, Author

@pytest.mark.asyncio
async def test_repository_add_and_get(test_db):
    # Setup factory for this test
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    
    async with session_factory() as session:
        repo = SQLBookRepository(session)
        
        book = Book(
            id=BookId.next_id(),
            title=Title("Integration Test Book"),
            author=Author("Tester"),
            is_borrowed=False
        )
        
        # Add
        saved_book = await repo.add(book)
        await session.commit() # Commit manually as UoW usually does this
        
        assert saved_book.id == book.id
        assert saved_book.title == book.title
        
        # Get by ID
        fetched_book = await repo.get_by_id(book.id.value)
        assert fetched_book is not None
        assert fetched_book.id == book.id
        assert fetched_book.title.value == "Integration Test Book"

@pytest.mark.asyncio
async def test_repository_update(test_db):
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    
    async with session_factory() as session:
        repo = SQLBookRepository(session)
        
        book = Book(
            id=BookId.next_id(),
            title=Title("Update Test Book"),
            author=Author("Tester"),
            is_borrowed=False
        )
        await repo.add(book)
        await session.commit()
        
        # Update
        book.borrow()
        await repo.update(book)
        await session.commit()
        
        # Verify
        fetched_book = await repo.get_by_id(book.id.value)
        assert fetched_book.is_borrowed is True
