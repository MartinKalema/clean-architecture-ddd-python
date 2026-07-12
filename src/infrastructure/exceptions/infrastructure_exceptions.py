from typing import Optional


class InfrastructureException(Exception):
    """Base class for all infrastructure exceptions."""


class DatabaseException(InfrastructureException):
    """Raised when a database operation fails."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception


class EventDispatcherException(InfrastructureException):
    """Raised when dispatching an event fails."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception


class MessageBrokerException(InfrastructureException):
    """Raised when a message broker operation fails."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception


class UnrecoverableMessageException(MessageBrokerException):
    """Raised when retry cannot make a malformed message processable."""


class DurableMessageHandlingException(MessageBrokerException):
    """Raised when a state transition must retry until it converges."""


class SearchEngineException(InfrastructureException):
    """Raised when a search engine operation fails."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception


class TemplateRenderingException(InfrastructureException):
    """Raised when rendering a template fails."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception

class ConfigurationException(InfrastructureException):
    """Raised when a configuration error occurs."""


class CircuitBreakerOpenException(InfrastructureException):
    """Raised when circuit breaker is open and rejecting requests."""
    def __init__(self, name: str, time_remaining: float):
        self.name = name
        self.time_remaining = time_remaining
        super().__init__(
            f"Circuit breaker '{name}' is OPEN. "
            f"Retry in {time_remaining:.1f} seconds."
        )
