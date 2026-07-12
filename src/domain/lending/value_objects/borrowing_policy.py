"""Lending-owned policy derived from upstream membership facts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BorrowingTerms:
    """Terms Lending applies while accepting a new loan."""

    max_outstanding_loans: int
    loan_duration_days: int


class LendingPolicy:
    """Translate an ACL membership fact into local Lending rules."""

    _TERMS = {
        "regular": BorrowingTerms(max_outstanding_loans=5, loan_duration_days=14),
        "premium": BorrowingTerms(max_outstanding_loans=10, loan_duration_days=21),
        "researcher": BorrowingTerms(
            max_outstanding_loans=20,
            loan_duration_days=30,
        ),
    }

    @classmethod
    def for_membership_tier(cls, membership_tier: str) -> BorrowingTerms | None:
        """Return local terms, or ``None`` for an unsupported upstream fact."""
        return cls._TERMS.get(str(membership_tier).strip().lower())
