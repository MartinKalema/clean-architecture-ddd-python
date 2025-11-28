"""
Shared kernel exceptions used across all bounded contexts.
"""


class DomainException(Exception):
    """Base class for all domain exceptions."""
    pass


class ValidationException(DomainException):
    """Raised when domain validation fails."""
    def __init__(self, message: str):
        super().__init__(message)


class InvalidEmailException(ValidationException):
    """Raised when an email address is invalid."""
    def __init__(self, email: str):
        super().__init__(f"Invalid email address: {email}")


class EmptyValueException(ValidationException):
    """Raised when a required value is empty."""
    def __init__(self, field_name: str):
        super().__init__(f"{field_name} cannot be empty")
