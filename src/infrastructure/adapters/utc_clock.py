"""Production UTC clock adapter."""
from datetime import datetime, timezone


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
