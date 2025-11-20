import pytest
from src.domain.entities.book import Book
from src.domain.value_objects.book_value_objects import BookId, Title, Author
from src.domain.events.book_events import BookBorrowed
from src.domain.exceptions.book_exceptions import BookAlreadyBorrowedException

def test_book_creation():
    book = Book(
        id=BookId.next_id(),
        title=Title("Clean Architecture"),
        author=Author("Uncle Bob"),
        is_borrowed=False
    )
    assert book.title.value == "Clean Architecture"
    assert book.is_borrowed is False

def test_mark_as_borrowed():
    book = Book(
        id=BookId.next_id(),
        title=Title("Clean Architecture"),
        author=Author("Uncle Bob"),
        is_borrowed=False
    )
    
    book.borrow()
    
    assert book.is_borrowed is True
    events = book.get_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], BookBorrowed)
    assert events[0].book_id == book.id.value

def test_borrow_already_borrowed():
    book = Book(
        id=BookId.next_id(),
        title=Title("Clean Architecture"),
        author=Author("Uncle Bob"),
        is_borrowed=True
    )
    
    # Should raise exception
    with pytest.raises(BookAlreadyBorrowedException):
        book.borrow()
