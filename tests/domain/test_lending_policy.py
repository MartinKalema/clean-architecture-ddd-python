"""Lending owns capacity and duration rules for upstream membership facts."""

from src.domain.lending import LendingPolicy


def test_regular_terms():
    terms = LendingPolicy.for_membership_tier("regular")
    assert terms is not None
    assert terms.max_outstanding_loans == 5
    assert terms.loan_duration_days == 14


def test_membership_tier_terms_are_lending_rules():
    premium = LendingPolicy.for_membership_tier("premium")
    researcher = LendingPolicy.for_membership_tier("researcher")
    assert premium is not None and researcher is not None
    assert (premium.max_outstanding_loans, premium.loan_duration_days) == (10, 21)
    assert (researcher.max_outstanding_loans, researcher.loan_duration_days) == (20, 30)


def test_unknown_upstream_tier_has_no_implicit_default():
    assert LendingPolicy.for_membership_tier("future-tier") is None
