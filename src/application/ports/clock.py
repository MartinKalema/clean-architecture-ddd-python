"""Time source port used by application workflows."""
from datetime import datetime
from typing import Protocol


class IClock(Protocol):
    """Returns timezone-aware UTC instants."""

    def now(self) -> datetime:
        ...
