from datetime import datetime as _datetime, timezone

import pytest

from src.domain.lending import (
    BookOverdue,
    CannotExtendOverdueLoanException,
    InvalidLoanDurationException,
    InvalidLoanExtensionException,
    InvalidLoanReturnDateException,
    InvalidReservationGenerationException,
    Loan,
    LoanCancelled,
    LoanCompleted,
    LoanCreated,
    LoanExtended,
    LoanNotActiveException,
    LoanNotOverdueException,
    LoanStatus,
)


RESERVATION_ID = "a527db31-754b-4633-8164-8c3edec329af"


def datetime(*args, **kwargs):
    """Keep every domain timestamp explicit and UTC-aware in this module."""
    kwargs.setdefault("tzinfo", timezone.utc)
    return _datetime(*args, **kwargs)


def _loan() -> Loan:
    return Loan.create(
        patron_id="patron-123",
        patron_email="patron@example.com",
        catalog_book_id="book-456",
        book_title="Clean Architecture",
        loan_duration_days=14,
        borrowed_at=datetime(2024, 1, 15, 10, 0),
        reservation_id=RESERVATION_ID,
        reservation_generation=3,
    )


class TestLoanCreation:
    def test_create_loan_with_correlation_event(self):
        loan = _loan()

        assert loan.patron_id == "patron-123"
        assert loan.catalog_book_id == "book-456"
        assert loan.reservation_id.value == RESERVATION_ID
        assert loan.reservation_generation == 3
        assert loan.status == LoanStatus.ACTIVE
        assert loan.returned_at is None
        assert loan.due_date.value == datetime(2024, 1, 29, 10, 0)

        events = loan.get_domain_events()
        assert len(events) == 1
        assert isinstance(events[0], LoanCreated)
        assert events[0].loan_id == loan.id.value
        assert events[0].reservation_id == RESERVATION_ID
        assert events[0].reservation_generation == 3
        assert events[0].patron_id == "patron-123"

    def test_generation_must_be_positive(self):
        with pytest.raises(InvalidReservationGenerationException):
            Loan.create(
                patron_id="patron-123",
                patron_email="patron@example.com",
                catalog_book_id="book-456",
                book_title="Clean Architecture",
                loan_duration_days=14,
                borrowed_at=datetime(2024, 1, 15, 10, 0),
                reservation_id=RESERVATION_ID,
                reservation_generation=0,
            )

    @pytest.mark.parametrize("days", [0, -1, -30])
    def test_loan_duration_must_be_positive(self, days: int):
        with pytest.raises(InvalidLoanDurationException):
            Loan.create(
                patron_id="patron-123",
                patron_email="patron@example.com",
                catalog_book_id="book-456",
                book_title="Clean Architecture",
                loan_duration_days=days,
                borrowed_at=datetime(2024, 1, 15, 10, 0),
                reservation_id=RESERVATION_ID,
                reservation_generation=1,
            )


class TestReturnBook:
    def test_return_book_creates_correlated_event(self):
        loan = _loan()
        loan.clear_events()

        returned_at = datetime(2024, 1, 20, 10, 0)
        loan.return_book(returned_at)

        assert loan.status == LoanStatus.RETURNED
        assert loan.returned_at == returned_at
        event = loan.get_domain_events()[0]
        assert isinstance(event, LoanCompleted)
        assert event.loan_id == loan.id.value
        assert event.reservation_id == RESERVATION_ID
        assert event.reservation_generation == 3
        assert event.was_overdue is False

    def test_return_overdue_book_sets_was_overdue_flag(self):
        loan = _loan()
        loan.clear_events()

        loan.return_book(datetime(2024, 2, 15, 10, 0))

        assert loan.get_domain_events()[0].was_overdue is True

    def test_return_already_returned_is_idempotent(self):
        loan = _loan()
        assert loan.return_book(datetime(2024, 1, 20, 10, 0)) is True
        loan.clear_events()

        assert loan.return_book(datetime(2024, 1, 21, 10, 0)) is False
        assert loan.returned_at == datetime(2024, 1, 20, 10, 0)
        assert loan.get_domain_events() == []

    def test_return_before_borrow_is_rejected_without_mutation(self):
        loan = _loan()
        loan.clear_events()

        with pytest.raises(InvalidLoanReturnDateException):
            loan.return_book(datetime(2024, 1, 14, 10, 0))

        assert loan.status == LoanStatus.ACTIVE
        assert loan.returned_at is None
        assert loan.get_domain_events() == []


class TestCancellation:
    def test_cancel_is_a_distinct_terminal_state_and_event(self):
        loan = _loan()
        loan.clear_events()

        assert loan.cancel("catalog reservation expired") is True

        assert loan.status == LoanStatus.CANCELLED
        assert loan.returned_at is None
        event = loan.get_domain_events()[0]
        assert isinstance(event, LoanCancelled)
        assert event.reservation_id == RESERVATION_ID
        assert event.reservation_generation == 3
        assert event.reason == "catalog reservation expired"

    def test_cancel_redelivery_is_idempotent(self):
        loan = _loan()
        loan.cancel("catalog reservation expired")
        loan.clear_events()

        assert loan.cancel("redelivery") is False
        assert loan.get_domain_events() == []

    def test_cancelled_loan_cannot_be_returned(self):
        loan = _loan()
        loan.cancel("catalog reservation expired")

        with pytest.raises(LoanNotActiveException):
            loan.return_book(datetime(2024, 1, 20, 10, 0))


class TestMarkOverdue:
    def test_mark_overdue_creates_event(self):
        loan = _loan()
        loan.clear_events()

        loan.mark_overdue(datetime(2024, 2, 1, 10, 0))

        assert loan.status == LoanStatus.OVERDUE
        event = loan.get_domain_events()[0]
        assert isinstance(event, BookOverdue)
        assert event.days_overdue == 3

    def test_mark_overdue_not_active_raises_exception(self):
        loan = _loan()
        loan.return_book(datetime(2024, 1, 20, 10, 0))

        with pytest.raises(LoanNotActiveException):
            loan.mark_overdue(datetime(2024, 2, 1, 10, 0))

    def test_mark_overdue_not_past_due_raises_exception(self):
        with pytest.raises(LoanNotOverdueException):
            _loan().mark_overdue(datetime(2024, 1, 20, 10, 0))


class TestExtend:
    def test_extend_loan_creates_event(self):
        loan = _loan()
        loan.clear_events()

        loan.extend(days=7, current_time=datetime(2024, 1, 25, 10, 0))

        assert loan.due_date.value == datetime(2024, 2, 5, 10, 0)
        event = loan.get_domain_events()[0]
        assert isinstance(event, LoanExtended)
        assert event.new_due_date == loan.due_date.value

    def test_extend_not_active_raises_exception(self):
        loan = _loan()
        loan.return_book(datetime(2024, 1, 20, 10, 0))

        with pytest.raises(LoanNotActiveException):
            loan.extend(days=7, current_time=datetime(2024, 1, 21, 10, 0))

    def test_extend_overdue_raises_exception(self):
        with pytest.raises(CannotExtendOverdueLoanException):
            _loan().extend(days=7, current_time=datetime(2024, 2, 1, 10, 0))

    @pytest.mark.parametrize("days", [0, -1, -30])
    def test_non_positive_extension_is_rejected(self, days: int):
        loan = _loan()
        original_due_date = loan.due_date
        loan.clear_events()

        with pytest.raises(InvalidLoanExtensionException):
            loan.extend(days=days, current_time=datetime(2024, 1, 20, 10, 0))

        assert loan.due_date == original_due_date
        assert loan.get_domain_events() == []


class TestIsOverdue:
    def test_is_overdue_when_active_and_past_due(self):
        assert _loan().is_overdue_as_of(datetime(2024, 2, 1, 10, 0)) is True

    def test_is_not_overdue_when_before_due(self):
        assert _loan().is_overdue_as_of(datetime(2024, 1, 20, 10, 0)) is False

    def test_is_not_overdue_when_returned(self):
        loan = _loan()
        loan.return_book(datetime(2024, 1, 20, 10, 0))

        assert loan.is_overdue_as_of(datetime(2024, 2, 1, 10, 0)) is False
