from datetime import datetime as _datetime, timedelta, timezone

import pytest

from src.domain.lending import DueDate, InvalidLoanIdException, LoanId, LoanStatus


def datetime(*args, **kwargs):
    kwargs.setdefault("tzinfo", timezone.utc)
    return _datetime(*args, **kwargs)


class TestLoanId:
    def test_creation(self):
        loan_id = LoanId.next_id()
        assert loan_id.value is not None
        assert isinstance(loan_id.value, str)

    def test_empty_validation(self):
        with pytest.raises(InvalidLoanIdException, match="LoanId cannot be empty"):
            LoanId("")

    def test_equality(self):
        loan_id = LoanId("loan-123")
        same_id = LoanId("loan-123")
        different_id = LoanId("loan-456")

        assert loan_id == same_id
        assert loan_id != different_id


class TestDueDate:
    def test_from_loan_duration(self):
        loan_date = datetime(2024, 1, 15, 10, 0)
        due_date = DueDate.from_loan_duration(loan_date, days=14)

        expected = datetime(2024, 1, 29, 10, 0)
        assert due_date.value == expected

    def test_is_overdue_when_past_due(self):
        due_date = DueDate(datetime(2024, 1, 15, 10, 0))
        current_time = datetime(2024, 1, 16, 10, 0)

        assert due_date.is_overdue_as_of(current_time) is True

    def test_is_not_overdue_when_before_due(self):
        due_date = DueDate(datetime(2024, 1, 15, 10, 0))
        current_time = datetime(2024, 1, 14, 10, 0)

        assert due_date.is_overdue_as_of(current_time) is False

    def test_is_not_overdue_when_exactly_on_due(self):
        due_date = DueDate(datetime(2024, 1, 15, 10, 0))
        current_time = datetime(2024, 1, 15, 10, 0)

        assert due_date.is_overdue_as_of(current_time) is False

    def test_days_until_due_positive(self):
        due_date = DueDate(datetime(2024, 1, 20, 10, 0))
        current_time = datetime(2024, 1, 15, 10, 0)

        assert due_date.days_until_due_as_of(current_time) == 5

    def test_days_until_due_negative_when_overdue(self):
        due_date = DueDate(datetime(2024, 1, 15, 10, 0))
        current_time = datetime(2024, 1, 20, 10, 0)

        assert due_date.days_until_due_as_of(current_time) == -5

    def test_extend(self):
        original = DueDate(datetime(2024, 1, 15, 10, 0))
        extended = original.extend(days=7)

        assert extended.value == datetime(2024, 1, 22, 10, 0)
        assert original.value == datetime(2024, 1, 15, 10, 0)

    def test_equality(self):
        due1 = DueDate(datetime(2024, 1, 15, 10, 0))
        due2 = DueDate(datetime(2024, 1, 15, 10, 0))
        due3 = DueDate(datetime(2024, 1, 16, 10, 0))

        assert due1 == due2
        assert due1 != due3


class TestLoanStatus:
    def test_status_values(self):
        assert LoanStatus.ACTIVE.value == "active"
        assert LoanStatus.RETURNED.value == "returned"
        assert LoanStatus.OVERDUE.value == "overdue"
        assert LoanStatus.LOST.value == "lost"

    def test_all_statuses_exist(self):
        statuses = [s.value for s in LoanStatus]
        assert "active" in statuses
        assert "returned" in statuses
        assert "overdue" in statuses
        assert "lost" in statuses
