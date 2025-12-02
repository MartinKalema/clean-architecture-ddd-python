import pytest

from src.domain.catalog import (
    Author,
    Book,
    BookAlreadyBorrowedException,
    BookBorrowed,
    BookId,
    Title,
)


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

    book.borrow("borrower@example.com")

    assert book.is_borrowed is True
    events = book.get_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], BookBorrowed)
    assert events[0].book_id == book.id.value
    assert events[0].borrower_email == "borrower@example.com"


def test_borrow_already_borrowed():
    book = Book(
        id=BookId.next_id(),
        title=Title("Clean Architecture"),
        author=Author("Uncle Bob"),
        is_borrowed=True
    )

    # Should raise exception
    with pytest.raises(BookAlreadyBorrowedException):
        book.borrow("borrower@example.com")
