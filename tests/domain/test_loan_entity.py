from datetime import datetime, timedelta

import pytest

from src.domain.lending import (
    BookOverdue,
    CannotExtendOverdueLoanException,
    Loan,
    LoanAlreadyReturnedException,
    LoanCompleted,
    LoanCreated,
    LoanExtended,
    LoanNotActiveException,
    LoanNotOverdueException,
    LoanStatus,
)


class TestLoanCreation:
    def test_create_loan_with_event(self):
        borrowed_at = datetime(2024, 1, 15, 10, 0)

        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=borrowed_at,
        )

        assert loan.patron_id == "patron-123"
        assert loan.patron_email == "patron@example.com"
        assert loan.catalog_book_id == "book-456"
        assert loan.book_title == "Clean Architecture"
        assert loan.borrowed_at == borrowed_at
        assert loan.status == LoanStatus.ACTIVE
        assert loan.returned_at is None
        assert loan.due_date.value == datetime(2024, 1, 29, 10, 0)

        events = loan.get_domain_events()
        assert len(events) == 1
        assert isinstance(events[0], LoanCreated)
        assert events[0].loan_id == loan.id.value
        assert events[0].patron_id == "patron-123"
        assert events[0].book_id == "book-456"


class TestReturnBook:
    def test_return_book_creates_event(self):
        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=datetime(2024, 1, 15, 10, 0),
        )
        loan.clear_events()

        returned_at = datetime(2024, 1, 20, 10, 0)
        loan.return_book(returned_at)

        assert loan.status == LoanStatus.RETURNED
        assert loan.returned_at == returned_at

        events = loan.get_domain_events()
        assert len(events) == 1
        assert isinstance(events[0], LoanCompleted)
        assert events[0].loan_id == loan.id.value
        assert events[0].was_overdue is False

    def test_return_overdue_book_sets_was_overdue_flag(self):
        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=datetime(2024, 1, 15, 10, 0),
        )
        loan.clear_events()

        returned_at = datetime(2024, 2, 15, 10, 0)
        loan.return_book(returned_at)

        events = loan.get_domain_events()
        assert events[0].was_overdue is True

    def test_return_already_returned_raises_exception(self):
        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=datetime(2024, 1, 15, 10, 0),
        )
        loan.return_book(datetime(2024, 1, 20, 10, 0))

        with pytest.raises(LoanAlreadyReturnedException):
            loan.return_book(datetime(2024, 1, 21, 10, 0))


class TestMarkOverdue:
    def test_mark_overdue_creates_event(self):
        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=datetime(2024, 1, 15, 10, 0),
        )
        loan.clear_events()

        current_time = datetime(2024, 2, 1, 10, 0)
        loan.mark_overdue(current_time)

        assert loan.status == LoanStatus.OVERDUE

        events = loan.get_domain_events()
        assert len(events) == 1
        assert isinstance(events[0], BookOverdue)
        assert events[0].loan_id == loan.id.value
        assert events[0].patron_email == "patron@example.com"
        assert events[0].book_title == "Clean Architecture"
        assert events[0].days_overdue == 3

    def test_mark_overdue_not_active_raises_exception(self):
        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=datetime(2024, 1, 15, 10, 0),
        )
        loan.return_book(datetime(2024, 1, 20, 10, 0))

        with pytest.raises(LoanNotActiveException):
            loan.mark_overdue(datetime(2024, 2, 1, 10, 0))

    def test_mark_overdue_not_past_due_raises_exception(self):
        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=datetime(2024, 1, 15, 10, 0),
        )

        current_time = datetime(2024, 1, 20, 10, 0)

        with pytest.raises(LoanNotOverdueException):
            loan.mark_overdue(current_time)


class TestExtend:
    def test_extend_loan_creates_event(self):
        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=datetime(2024, 1, 15, 10, 0),
        )
        loan.clear_events()
        old_due_date = loan.due_date

        current_time = datetime(2024, 1, 25, 10, 0)
        loan.extend(days=7, current_time=current_time)

        assert loan.due_date.value == datetime(2024, 2, 5, 10, 0)

        events = loan.get_domain_events()
        assert len(events) == 1
        assert isinstance(events[0], LoanExtended)
        assert events[0].loan_id == loan.id.value
        assert events[0].old_due_date == old_due_date.value
        assert events[0].new_due_date == loan.due_date.value

    def test_extend_not_active_raises_exception(self):
        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=datetime(2024, 1, 15, 10, 0),
        )
        loan.return_book(datetime(2024, 1, 20, 10, 0))

        with pytest.raises(LoanNotActiveException):
            loan.extend(days=7, current_time=datetime(2024, 1, 21, 10, 0))

    def test_extend_overdue_raises_exception(self):
        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=datetime(2024, 1, 15, 10, 0),
        )

        current_time = datetime(2024, 2, 1, 10, 0)

        with pytest.raises(CannotExtendOverdueLoanException):
            loan.extend(days=7, current_time=current_time)


class TestIsOverdue:
    def test_is_overdue_when_past_due(self):
        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=datetime(2024, 1, 15, 10, 0),
        )

        current_time = datetime(2024, 2, 1, 10, 0)
        assert loan.is_overdue_as_of(current_time) is True

    def test_is_not_overdue_when_before_due(self):
        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=datetime(2024, 1, 15, 10, 0),
        )

        current_time = datetime(2024, 1, 20, 10, 0)
        assert loan.is_overdue_as_of(current_time) is False

    def test_is_not_overdue_when_returned(self):
        loan = Loan.create(
            patron_id="patron-123",
            patron_email="patron@example.com",
            catalog_book_id="book-456",
            book_title="Clean Architecture",
            loan_duration_days=14,
            borrowed_at=datetime(2024, 1, 15, 10, 0),
        )
        loan.return_book(datetime(2024, 1, 20, 10, 0))

        current_time = datetime(2024, 2, 1, 10, 0)
        assert loan.is_overdue_as_of(current_time) is False
