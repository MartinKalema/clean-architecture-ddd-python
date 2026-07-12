"""Persistence-boundary diagnostics for concurrent loan creation."""
from sqlalchemy.exc import IntegrityError

from src.infrastructure.adapters.lending.loan_unit_of_work import LoanUnitOfWork


class _DriverUniqueViolation(Exception):
    constraint_name = "ix_loans_reservation_id_unique"


def test_extracts_async_driver_constraint_name_from_exception_chain():
    wrapper = Exception("driver wrapper")
    wrapper.__cause__ = _DriverUniqueViolation("duplicate")
    error = IntegrityError("insert", {}, wrapper)

    assert (
        LoanUnitOfWork._constraint_name(error)
        == "ix_loans_reservation_id_unique"
    )
