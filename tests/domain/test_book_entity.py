from datetime import datetime

import pytest

from src.domain.catalog import (
    Author,
    Book,
    BookAlreadyBorrowedException,
    BookId,
    BookNotBorrowedException,
    BookNotReservedException,
    BookStatus,
    CatalogBookBorrowed,
    CatalogBookReleased,
    CatalogBookReserved,
    CatalogBookReturned,
    Title,
)


def _book() -> Book:
    return Book(
        id=BookId.next_id(),
        title=Title("Clean Architecture"),
        author=Author("Uncle Bob"),
    )


def test_book_creation():
    book = _book()
    assert book.title.value == "Clean Architecture"
    assert book.status == BookStatus.AVAILABLE
    assert book.is_borrowed is False


def test_reserve_holds_the_book_and_raises_event():
    book = _book()
    reserved_at = datetime.now()

    book.reserve("borrower@example.com", reserved_at)

    assert book.status == BookStatus.RESERVED
    assert book.is_borrowed is True  # withheld from other borrowers
    assert book.reserved_at == reserved_at
    events = book.get_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], CatalogBookReserved)
    assert events[0].book_id == book.id.value
    assert events[0].borrower_email == "borrower@example.com"


def test_reserve_rejects_non_available_book():
    book = _book()
    book.reserve("first@example.com", datetime.now())

    # Semantic lock: only one saga can hold the book
    with pytest.raises(BookAlreadyBorrowedException):
        book.reserve("second@example.com", datetime.now())


def test_confirm_borrow_finalizes_reservation():
    book = _book()
    book.reserve("borrower@example.com", datetime.now())
    book.clear_events()

    book.confirm_borrow("borrower@example.com")

    assert book.status == BookStatus.BORROWED
    assert book.reserved_at is None
    events = book.get_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], CatalogBookBorrowed)


def test_confirm_borrow_requires_reservation():
    with pytest.raises(BookNotReservedException):
        _book().confirm_borrow("borrower@example.com")


def test_release_returns_reservation_to_available():
    book = _book()
    book.reserve("borrower@example.com", datetime.now())
    book.clear_events()

    book.release("loan creation failed")

    assert book.status == BookStatus.AVAILABLE
    assert book.is_borrowed is False
    assert book.reserved_at is None
    assert book.return_due_date is None
    events = book.get_domain_events()
    assert isinstance(events[0], CatalogBookReleased)
    assert events[0].reason == "loan creation failed"


def test_mark_borrowed_claims_available_book():
    book = _book()
    borrowed_at = datetime(2026, 7, 4, 12, 0)
    due = datetime(2026, 7, 18, 12, 0)

    book.mark_borrowed("borrower@example.com", borrowed_at, due)

    assert book.status == BookStatus.BORROWED
    assert book.borrowed_at == borrowed_at
    assert book.return_due_date == due
    events = book.get_domain_events()
    assert isinstance(events[0], CatalogBookBorrowed)


def test_mark_borrowed_rejects_non_available_book():
    book = _book()
    book.reserve("first@example.com", datetime.now())

    with pytest.raises(BookAlreadyBorrowedException):
        book.mark_borrowed("second@example.com", datetime.now(), datetime.now())


def test_release_requires_reservation():
    book = _book()
    book.reserve("borrower@example.com", datetime.now())
    book.confirm_borrow("borrower@example.com")

    # A confirmed borrow is returned, not released
    with pytest.raises(BookNotReservedException):
        book.release("too late")


def test_return_book_after_confirmed_borrow():
    book = _book()
    book.reserve("borrower@example.com", datetime.now())
    book.confirm_borrow("borrower@example.com")
    book.clear_events()

    book.return_book()

    assert book.status == BookStatus.AVAILABLE
    assert isinstance(book.get_domain_events()[0], CatalogBookReturned)


def test_return_book_requires_confirmed_borrow():
    book = _book()
    book.reserve("borrower@example.com", datetime.now())

    # RESERVED is tentative: it is released, never returned
    with pytest.raises(BookNotBorrowedException):
        book.return_book()
