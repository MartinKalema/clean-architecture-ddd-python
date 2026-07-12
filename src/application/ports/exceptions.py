"""Failures defined by application port contracts."""


class EmailDeliveryException(Exception):
    """A deterministic provider rejection that retry cannot repair."""

    def __init__(
        self,
        message: str,
        original_exception: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.original_exception = original_exception
