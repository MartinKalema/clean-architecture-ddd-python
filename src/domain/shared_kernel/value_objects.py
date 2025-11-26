"""
Shared value objects used across multiple bounded contexts.

These are part of the Shared Kernel - any changes require coordination
between all bounded contexts that use them.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class EmailAddress:
    """
    Email address value object - used by Patron and Notification contexts.

    This is in the shared kernel because:
    - Patron context uses it for member contact info
    - Notification context uses it for sending emails
    - Lending context references it for borrower notifications
    """

    value: str

    def __post_init__(self):
        if not self.value or not self._is_valid_email(self.value):
            raise ValueError(f"Invalid email address: {self.value}")

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        """Basic email validation."""
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email))

    def __str__(self) -> str:
        return self.value
