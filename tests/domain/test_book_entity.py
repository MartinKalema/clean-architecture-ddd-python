from datetime import datetime, timedelta, timezone

import pytest

from src.domain.catalog import (
    Author,
    Book,
    BookAlreadyBorrowedException,
    BookId,
    BookStatus,
    CatalogBookBorrowed,
    CatalogBookReleased,
    CatalogBookReserved,
    CatalogBookReturned,
    LoanCorrelationMismatchException,
    StaleReservationException,
    Title,
)


def _book() -> Book:
    return Book(
        id=BookId.next_id(),
        title=Title("Clean Architecture"),
        author=Author("Uncle Bob"),
    )


def _reserve(
    book: Book,
    *,
    patron_id: str = "patron-123",
    email: str = "borrower@example.com",
):
    token = book.reserve(patron_id, email, datetime.now(timezone.utc))
    return token, book.reservation_generation


def _return(book: Book, loan_id: str) -> bool:
    assert book.reservation_id is not None
    assert book.reserved_patron_id is not None
    return book.return_book(
        loan_id,
        book.reservation_id,
        book.reservation_generation,
        book.reserved_patron_id,
    )


def _confirm(
    book: Book,
    token,
    generation: int,
    patron_id: str = "patron-123",
    loan_id: str = "loan-123",
) -> bool:
    assert book.reserved_at is not None
    borrowed_at = book.reserved_at
    return book.confirm_borrow(
        token,
        generation,
        patron_id,
        loan_id,
        borrowed_at,
        borrowed_at + timedelta(days=14),
    )


def test_book_creation():
    book = _book()
    assert book.title.value == "Clean Architecture"
    assert book.status == BookStatus.AVAILABLE
    assert book.is_borrowed is False
    assert book.reservation_generation == 0


def test_reserve_creates_identity_increments_fence_and_raises_event():
    book = _book()
    reserved_at = datetime.now(timezone.utc)

    token = book.reserve("patron-123", "borrower@example.com", reserved_at)

    assert book.status == BookStatus.RESERVED
    assert book.is_borrowed is False
    assert book.is_unavailable is True
    assert book.reserved_at == reserved_at
    assert book.reservation_id == token
    assert book.reservation_generation == 1
    assert book.reserved_patron_id == "patron-123"
    events = book.get_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], CatalogBookReserved)
    assert events[0].reservation_id == token.value
    assert events[0].reservation_generation == 1
    assert events[0].patron_id == "patron-123"
    assert events[0].borrower_email == "borrower@example.com"


def test_reserve_leaves_loan_dates_to_lending():
    book = _book()
    reserved_at = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)

    book.reserve("premium-patron", "premium@example.com", reserved_at)

    assert book.borrowed_at is None
    assert book.return_due_date is None
    assert not hasattr(book.get_domain_events()[0], "return_due_date")


def test_reserve_rejects_non_available_book():
    book = _book()
    _reserve(book)

    with pytest.raises(BookAlreadyBorrowedException):
        book.reserve(
            "patron-456",
            "second@example.com",
            datetime.now(timezone.utc),
        )


def test_each_new_reservation_increments_generation():
    book = _book()
    first, first_generation = _reserve(book)
    book.release(first, first_generation, "patron-123", "rejected")

    second, second_generation = _reserve(book, patron_id="patron-456")

    assert second != first
    assert second_generation == first_generation + 1


def test_confirm_borrow_requires_exact_reservation_and_records_loan():
    book = _book()
    token, generation = _reserve(book)
    book.clear_events()

    changed = _confirm(book, token, generation)

    assert changed is True
    assert book.status == BookStatus.BORROWED
    assert book.current_loan_id == "loan-123"
    assert book.reserved_at is None
    events = book.get_domain_events()
    assert len(events) == 1
    assert isinstance(events[0], CatalogBookBorrowed)
    assert events[0].reservation_id == token.value
    assert events[0].reservation_generation == generation
    assert events[0].patron_id == "patron-123"
    assert events[0].loan_id == "loan-123"
    assert events[0].borrower_email == "borrower@example.com"


def test_confirm_borrow_exact_redelivery_is_idempotent():
    book = _book()
    token, generation = _reserve(book)
    _confirm(book, token, generation)
    book.clear_events()

    assert book.borrowed_at is not None
    changed = book.confirm_borrow(
        token,
        generation,
        "patron-123",
        "loan-123",
        book.borrowed_at,
        book.return_due_date,
    )

    assert changed is False
    assert book.get_domain_events() == []


def test_delayed_confirmation_cannot_claim_a_newer_reservation():
    book = _book()
    old_token, old_generation = _reserve(book)
    book.release(old_token, old_generation, "patron-123", "timed out")
    new_token, new_generation = _reserve(book, patron_id="patron-456")

    with pytest.raises(StaleReservationException):
        book.confirm_borrow(
            old_token,
            old_generation,
            "patron-123",
            "stale-loan",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=14),
        )

    assert book.status == BookStatus.RESERVED
    assert book.reservation_id == new_token
    assert book.reservation_generation == new_generation
    assert book.reserved_patron_id == "patron-456"


def test_release_requires_exact_reservation_and_is_idempotent():
    book = _book()
    token, generation = _reserve(book)
    book.clear_events()

    changed = book.release(token, generation, "patron-123", "loan rejected")

    assert changed is True
    assert book.status == BookStatus.AVAILABLE
    assert book.return_due_date is None
    event = book.get_domain_events()[0]
    assert isinstance(event, CatalogBookReleased)
    assert event.reservation_id == token.value
    assert event.patron_id == "patron-123"

    book.clear_events()
    assert (
        book.release(token, generation, "patron-123", "redelivery") is False
    )
    assert book.get_domain_events() == []


def test_delayed_release_cannot_release_a_newer_reservation():
    book = _book()
    old_token, old_generation = _reserve(book)
    book.release(old_token, old_generation, "patron-123", "first failure")
    new_token, _ = _reserve(book, patron_id="patron-456")

    with pytest.raises(StaleReservationException):
        book.release(old_token, old_generation, "patron-123", "delayed")

    assert book.status == BookStatus.RESERVED
    assert book.reservation_id == new_token


def test_return_requires_current_loan_and_exact_duplicate_is_idempotent():
    book = _book()
    token, generation = _reserve(book)
    _confirm(book, token, generation)
    book.clear_events()

    assert _return(book, "loan-123") is True

    assert book.status == BookStatus.AVAILABLE
    assert book.current_loan_id is None
    assert book.last_completed_loan_id == "loan-123"
    event = book.get_domain_events()[0]
    assert isinstance(event, CatalogBookReturned)
    assert event.loan_id == "loan-123"

    book.clear_events()
    assert _return(book, "loan-123") is False
    assert book.get_domain_events() == []


def test_wrong_loan_cannot_return_book():
    book = _book()
    token, generation = _reserve(book)
    _confirm(book, token, generation)

    with pytest.raises(LoanCorrelationMismatchException):
        _return(book, "loan-456")

    assert book.status == BookStatus.BORROWED
    assert book.current_loan_id == "loan-123"


@pytest.mark.parametrize(
    ("reservation_id", "generation", "patron_id"),
    [
        ("11111111-1111-4111-8111-111111111111", 1, "patron-123"),
        (None, 999, "patron-123"),
        (None, 1, "different-patron"),
    ],
)
def test_return_requires_exact_reservation_owner_and_generation(
    reservation_id, generation, patron_id
):
    book = _book()
    token, current_generation = _reserve(book)
    _confirm(book, token, current_generation)

    with pytest.raises(LoanCorrelationMismatchException):
        book.return_book(
            "loan-123",
            reservation_id or token,
            generation,
            patron_id,
        )

    assert book.status == BookStatus.BORROWED
    assert book.current_loan_id == "loan-123"
