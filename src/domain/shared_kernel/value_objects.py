"""
Shared value objects used across multiple bounded contexts.

These are part of the Shared Kernel - any changes require coordination
between all bounded contexts that use them.
"""
import re
from dataclasses import dataclass

from src.domain.shared_kernel.exceptions import InvalidEmailException


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
        value = str(self.value).strip().lower()
        if len(value) > 254 or not self._is_valid_email(value):
            raise InvalidEmailException(value)
        object.__setattr__(self, "value", value)

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        """Basic email validation."""
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.fullmatch(pattern, email))

    def __str__(self) -> str:
        return self.value
