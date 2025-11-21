class InfrastructureException(Exception):
    """Base class for all infrastructure exceptions."""
    pass

class DatabaseException(InfrastructureException):
    """Raised when a database operation fails."""
    def __init__(self, message: str, original_exception: Exception = None):
        super().__init__(message)
        self.original_exception = original_exception
