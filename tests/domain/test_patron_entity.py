from datetime import datetime

import pytest

from src.domain.patron import (
    InvalidTierUpgradeException,
    MembershipTier,
    Patron,
    PatronAlreadySuspendedException,
    PatronName,
    PatronNotSuspendedException,
    PatronRegistered,
    PatronReinstated,
    PatronSuspended,
)
from src.domain.shared_kernel import EmailAddress


class TestPatronCreation:
    def test_register_creates_patron_with_event(self):
        name = PatronName(first_name="John", last_name="Doe")
        email = EmailAddress("john.doe@example.com")
        registered_at = datetime(2024, 1, 15, 10, 30)

        patron = Patron.register(
            name=name,
            email=email,
            registered_at=registered_at,
        )

        assert patron.name == name
        assert patron.email == email
        assert patron.registered_at == registered_at
        assert patron.membership_tier == MembershipTier.REGULAR
        assert patron.is_suspended is False
        assert patron.suspended_reason is None

        events = patron.get_domain_events()
        assert len(events) == 1
        assert isinstance(events[0], PatronRegistered)
        assert events[0].patron_id == patron.id.value
        assert events[0].email == "john.doe@example.com"
        assert events[0].name == "John Doe"

    def test_register_with_premium_tier(self):
        patron = Patron.register(
            name=PatronName(first_name="Jane", last_name="Smith"),
            email=EmailAddress("jane@example.com"),
            registered_at=datetime.now(),
            membership_tier=MembershipTier.PREMIUM,
        )

        assert patron.membership_tier == MembershipTier.PREMIUM


class TestCanBorrow:
    def test_can_borrow_when_under_limit(self):
        patron = Patron.register(
            name=PatronName(first_name="John", last_name="Doe"),
            email=EmailAddress("john@example.com"),
            registered_at=datetime.now(),
        )

        assert patron.can_borrow(current_loans=0) is True
        assert patron.can_borrow(current_loans=4) is True

    def test_cannot_borrow_when_at_limit(self):
        patron = Patron.register(
            name=PatronName(first_name="John", last_name="Doe"),
            email=EmailAddress("john@example.com"),
            registered_at=datetime.now(),
        )

        assert patron.can_borrow(current_loans=5) is False
        assert patron.can_borrow(current_loans=6) is False

    def test_cannot_borrow_when_suspended(self):
        patron = Patron.register(
            name=PatronName(first_name="John", last_name="Doe"),
            email=EmailAddress("john@example.com"),
            registered_at=datetime.now(),
        )
        patron.suspend("Late returns")
        patron.clear_events()

        assert patron.can_borrow(current_loans=0) is False

    def test_premium_tier_higher_limit(self):
        patron = Patron.register(
            name=PatronName(first_name="John", last_name="Doe"),
            email=EmailAddress("john@example.com"),
            registered_at=datetime.now(),
            membership_tier=MembershipTier.PREMIUM,
        )

        assert patron.can_borrow(current_loans=5) is True
        assert patron.can_borrow(current_loans=9) is True
        assert patron.can_borrow(current_loans=10) is False


class TestSuspend:
    def test_suspend_patron(self):
        patron = Patron.register(
            name=PatronName(first_name="John", last_name="Doe"),
            email=EmailAddress("john@example.com"),
            registered_at=datetime.now(),
        )
        patron.clear_events()

        patron.suspend("Multiple late returns")

        assert patron.is_suspended is True
        assert patron.suspended_reason == "Multiple late returns"

        events = patron.get_domain_events()
        assert len(events) == 1
        assert isinstance(events[0], PatronSuspended)
        assert events[0].patron_id == patron.id.value
        assert events[0].reason == "Multiple late returns"

    def test_suspend_already_suspended_raises_exception(self):
        patron = Patron.register(
            name=PatronName(first_name="John", last_name="Doe"),
            email=EmailAddress("john@example.com"),
            registered_at=datetime.now(),
        )
        patron.suspend("First suspension")

        with pytest.raises(PatronAlreadySuspendedException):
            patron.suspend("Second suspension")


class TestReinstate:
    def test_reinstate_suspended_patron(self):
        patron = Patron.register(
            name=PatronName(first_name="John", last_name="Doe"),
            email=EmailAddress("john@example.com"),
            registered_at=datetime.now(),
        )
        patron.suspend("Late returns")
        patron.clear_events()

        patron.reinstate()

        assert patron.is_suspended is False
        assert patron.suspended_reason is None

        events = patron.get_domain_events()
        assert len(events) == 1
        assert isinstance(events[0], PatronReinstated)
        assert events[0].patron_id == patron.id.value

    def test_reinstate_non_suspended_raises_exception(self):
        patron = Patron.register(
            name=PatronName(first_name="John", last_name="Doe"),
            email=EmailAddress("john@example.com"),
            registered_at=datetime.now(),
        )

        with pytest.raises(PatronNotSuspendedException):
            patron.reinstate()


class TestUpgradeTier:
    def test_upgrade_from_regular_to_premium(self):
        patron = Patron.register(
            name=PatronName(first_name="John", last_name="Doe"),
            email=EmailAddress("john@example.com"),
            registered_at=datetime.now(),
            membership_tier=MembershipTier.REGULAR,
        )

        patron.upgrade_tier(MembershipTier.PREMIUM)

        assert patron.membership_tier == MembershipTier.PREMIUM

    def test_upgrade_from_premium_to_researcher(self):
        patron = Patron.register(
            name=PatronName(first_name="John", last_name="Doe"),
            email=EmailAddress("john@example.com"),
            registered_at=datetime.now(),
            membership_tier=MembershipTier.PREMIUM,
        )

        patron.upgrade_tier(MembershipTier.RESEARCHER)

        assert patron.membership_tier == MembershipTier.RESEARCHER

    def test_upgrade_to_same_tier_raises_exception(self):
        patron = Patron.register(
            name=PatronName(first_name="John", last_name="Doe"),
            email=EmailAddress("john@example.com"),
            registered_at=datetime.now(),
            membership_tier=MembershipTier.PREMIUM,
        )

        with pytest.raises(InvalidTierUpgradeException):
            patron.upgrade_tier(MembershipTier.PREMIUM)

    def test_downgrade_raises_exception(self):
        patron = Patron.register(
            name=PatronName(first_name="John", last_name="Doe"),
            email=EmailAddress("john@example.com"),
            registered_at=datetime.now(),
            membership_tier=MembershipTier.PREMIUM,
        )

        with pytest.raises(InvalidTierUpgradeException):
            patron.upgrade_tier(MembershipTier.REGULAR)
