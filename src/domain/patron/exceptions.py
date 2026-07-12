"""
Exceptions for the Patron bounded context.
"""
from src.domain.shared_kernel.exceptions import DomainException


class PatronException(DomainException):
    """Base class for patron domain exceptions."""


class PatronAlreadySuspendedException(PatronException):
    """Raised when attempting to suspend an already suspended patron."""
    def __init__(self, patron_id: str):
        super().__init__(f"Patron {patron_id} is already suspended")


class PatronNotSuspendedException(PatronException):
    """Raised when attempting to reinstate a patron who is not suspended."""
    def __init__(self, patron_id: str):
        super().__init__(f"Patron {patron_id} is not suspended")


class InvalidTierUpgradeException(PatronException):
    """Raised when attempting to upgrade to a lower or equal tier."""
    def __init__(self, current_tier: str, requested_tier: str):
        super().__init__(
            f"Cannot upgrade from {current_tier} to {requested_tier}: "
            "can only upgrade to a higher tier"
        )


class InvalidPatronIdException(PatronException):
    """Raised when a patron ID is invalid."""
    def __init__(self):
        super().__init__("PatronId cannot be empty")


class InvalidPatronNameException(PatronException):
    """Raised when a patron name is invalid."""
    def __init__(self, field: str, detail: str = "cannot be empty"):
        super().__init__(f"{field} {detail}")


class InvalidSuspensionReasonException(PatronException):
    """Raised when a suspension reason is blank or unbounded."""

    def __init__(self):
        super().__init__("Suspension reason must be between 1 and 500 characters")


class InvalidPatronStateException(PatronException):
    """Raised when construction/rehydration violates Patron invariants."""

    def __init__(self, detail: str):
        super().__init__(f"Invalid patron state: {detail}")


class PatronEmailAlreadyRegisteredException(PatronException):
    """Raised when normalized patron email uniqueness is violated."""

    def __init__(self, email: str):
        self.email = email
        super().__init__(f"A patron with email {email} is already registered")


class PatronNotFoundException(PatronException):
    """Raised when a patron is not found."""
    def __init__(self, patron_id: str):
        super().__init__(f"Patron with id {patron_id} not found")


class ConcurrentModificationException(PatronException):
    """Raised when optimistic locking fails."""
    def __init__(self, patron_id: str):
        super().__init__(f"Patron {patron_id} was modified by another process")
