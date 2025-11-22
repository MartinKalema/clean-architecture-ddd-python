class InfrastructureException(Exception):
    """Base class for all infrastructure exceptions."""
    pass

class DatabaseException(InfrastructureException):
    """Raised when a database operation fails."""
    def __init__(self, message: str, original_exception: Exception = None):
        super().__init__(message)
        self.original_exception = original_exception

class EmailServiceException(InfrastructureException):
    """Raised when sending an email fails."""
    def __init__(self, message: str, original_exception: Exception = None):
        super().__init__(message)
        self.original_exception = original_exception

class EventDispatcherException(InfrastructureException):
    """Raised when dispatching an event fails."""
    def __init__(self, message: str, original_exception: Exception = None):
        super().__init__(message)
        self.original_exception = original_exception

class TemplateRenderingException(InfrastructureException):
    """Raised when rendering a template fails."""
    def __init__(self, message: str, original_exception: Exception = None):
        super().__init__(message)
        self.original_exception = original_exception

class ConfigurationException(InfrastructureException):
    """Raised when a configuration error occurs."""
    pass
