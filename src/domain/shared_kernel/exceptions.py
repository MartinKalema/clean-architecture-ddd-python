"""
Shared kernel exceptions used across all bounded contexts.
"""


class DomainException(Exception):
    """Base class for all domain exceptions."""


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


class EmailDeliveryException(Exception):
    """
    Raised by IEmailService implementations when the provider permanently
    rejects a send (bad credentials, invalid recipient, rejected content).

    Part of the IEmailService port contract: callers can distinguish this
    from transient failures (timeouts, open circuit breaker), which
    propagate as other exception types and are worth retrying.
    """
    def __init__(self, message: str, original_exception: "Exception | None" = None):
        super().__init__(message)
        self.original_exception = original_exception
