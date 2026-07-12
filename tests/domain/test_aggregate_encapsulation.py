"""Aggregate state changes are reachable only through domain behavior."""
from datetime import datetime, timedelta, timezone

import pytest

from src.domain.catalog import (
    Author,
    Book,
    BookStatus,
    InvalidCatalogStateException,
    Title,
)
from src.domain.lending import (
    DueDate,
    InvalidLoanStateException,
    Loan,
    LoanStatus,
    ReservationId,
)
from src.domain.patron import InvalidPatronStateException, Patron, PatronName
from src.domain.shared_kernel import EmailAddress


NOW = datetime(2026, 7, 11, tzinfo=timezone.utc)
RESERVATION_ID = "11111111-1111-4111-8111-111111111111"


def test_book_public_state_is_read_only_but_transition_can_change_it():
    book = Book(title=Title("DDD"), author=Author("Eric Evans"))

    with pytest.raises(AttributeError, match="aggregate transition"):
        book.status = BookStatus.BORROWED

    book.reserve("patron-1", "patron@example.com", NOW)
    assert book.status == BookStatus.RESERVED


def test_loan_public_state_is_read_only_but_transition_can_change_it():
    loan = Loan.create(
        patron_id="patron-1",
        patron_email="patron@example.com",
        catalog_book_id="book-1",
        book_title="DDD",
        loan_duration_days=14,
        borrowed_at=NOW,
        reservation_id=RESERVATION_ID,
        reservation_generation=1,
    )

    with pytest.raises(AttributeError, match="aggregate transition"):
        loan.status = LoanStatus.RETURNED

    assert loan.return_book(NOW) is True
    assert loan.status == LoanStatus.RETURNED


def test_patron_public_state_is_read_only_but_transition_can_change_it():
    patron = Patron.register(
        name=PatronName("Test", "Patron"),
        email=EmailAddress("patron@example.com"),
        registered_at=NOW,
    )

    with pytest.raises(AttributeError, match="aggregate transition"):
        patron.is_suspended = True

    patron.suspend("policy")
    assert patron.is_suspended is True


def test_impossible_aggregate_states_cannot_be_constructed():
    with pytest.raises(InvalidCatalogStateException):
        Book(
            title=Title("DDD"),
            author=Author("Eric Evans"),
            status=BookStatus.BORROWED,
        )

    with pytest.raises(InvalidLoanStateException):
        Loan(
            patron_id="patron-1",
            patron_email="patron@example.com",
            catalog_book_id="book-1",
            book_title="DDD",
            due_date=DueDate(NOW + timedelta(days=14)),
            borrowed_at=NOW,
            reservation_id=ReservationId(RESERVATION_ID),
            reservation_generation=1,
            status=LoanStatus.RETURNED,
        )

    with pytest.raises(InvalidPatronStateException):
        Patron(
            name=PatronName("Test", "Patron"),
            email=EmailAddress("patron@example.com"),
            registered_at=NOW,
            is_suspended=True,
            suspended_reason=None,
        )
