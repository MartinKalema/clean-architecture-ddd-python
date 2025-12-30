import pytest

from src.domain.patron import (
    InvalidPatronIdException,
    InvalidPatronNameException,
    MembershipTier,
    PatronId,
    PatronName,
)


class TestPatronId:
    def test_creation(self):
        patron_id = PatronId.next_id()
        assert patron_id.value is not None
        assert isinstance(patron_id.value, str)

    def test_empty_validation(self):
        with pytest.raises(InvalidPatronIdException, match="PatronId cannot be empty"):
            PatronId("")

    def test_equality(self):
        patron_id = PatronId("abc-123")
        same_id = PatronId("abc-123")
        different_id = PatronId("xyz-789")

        assert patron_id == same_id
        assert patron_id != different_id


class TestPatronName:
    def test_creation(self):
        name = PatronName(first_name="John", last_name="Doe")
        assert name.first_name == "John"
        assert name.last_name == "Doe"

    def test_full_name_property(self):
        name = PatronName(first_name="John", last_name="Doe")
        assert name.full_name == "John Doe"

    def test_empty_first_name_validation(self):
        with pytest.raises(InvalidPatronNameException, match="First name cannot be empty"):
            PatronName(first_name="", last_name="Doe")

    def test_empty_last_name_validation(self):
        with pytest.raises(InvalidPatronNameException, match="Last name cannot be empty"):
            PatronName(first_name="John", last_name="")

    def test_equality(self):
        name1 = PatronName(first_name="John", last_name="Doe")
        name2 = PatronName(first_name="John", last_name="Doe")
        name3 = PatronName(first_name="Jane", last_name="Doe")

        assert name1 == name2
        assert name1 != name3


class TestMembershipTier:
    def test_regular_tier_limits(self):
        tier = MembershipTier.REGULAR
        assert tier.borrowing_limit == 5
        assert tier.loan_duration_days == 14

    def test_premium_tier_limits(self):
        tier = MembershipTier.PREMIUM
        assert tier.borrowing_limit == 10
        assert tier.loan_duration_days == 21

    def test_researcher_tier_limits(self):
        tier = MembershipTier.RESEARCHER
        assert tier.borrowing_limit == 20
        assert tier.loan_duration_days == 30

    def test_tier_values(self):
        assert MembershipTier.REGULAR.value == "regular"
        assert MembershipTier.PREMIUM.value == "premium"
        assert MembershipTier.RESEARCHER.value == "researcher"
