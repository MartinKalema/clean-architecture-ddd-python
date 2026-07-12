"""Application-layer failures independent of transport and infrastructure."""


class ApplicationException(Exception):
    """Base class for application workflow errors."""


class IdempotencyKeyConflictException(ApplicationException):
    """A key was reused for a different request or is racing concurrently."""

    def __init__(self, key: str, detail: str = "request fingerprint differs"):
        self.key = key
        super().__init__(f"Idempotency key {key!r} conflicts: {detail}")


class InvalidIdempotencyKeyException(ApplicationException):
    """The transport supplied an idempotency key outside the public contract."""

    def __init__(self, detail: str = "must be 8-128 URL/log-safe characters"):
        super().__init__(f"Invalid idempotency key: {detail}")


class BorrowOperationNotFoundException(ApplicationException):
    """Raised when a requested borrow workflow identity is unknown."""

    def __init__(self, operation_id: str):
        super().__init__(f"Borrow operation {operation_id} not found")


class BorrowOperationTransitionException(ApplicationException):
    """Raised when a delayed workflow message targets the wrong operation state."""

    def __init__(self, operation_id: str, detail: str):
        self.operation_id = operation_id
        super().__init__(
            f"Borrow operation {operation_id} cannot be transitioned: {detail}"
        )
