"""
Production-Grade Load Test Suite.

Usage:
    # Smoke test (quick validation)
    locust -f tests/load/locustfile.py --headless -u 10 -r 2 -t 1m

    # Standard load test
    locust -f tests/load/locustfile.py --headless -u 100 -r 10 -t 5m

    # Stress test with custom shape
    locust -f tests/load/locustfile.py --headless -t 10m SpikeShape

    # Web UI for interactive testing
    locust -f tests/load/locustfile.py

    # Filter by tags
    locust -f tests/load/locustfile.py --tags read  # Only read operations
    locust -f tests/load/locustfile.py --exclude-tags admin  # Exclude admin ops
"""
from tests.load.scenarios import (
    BorrowerUser,
    BrowserUser,
    LibrarianUser,
    PatronManagerUser,
    StressTestUser,
)
from tests.load.shapes import (
    CircuitBreakerTestShape,
    SoakShape,
    SpikeShape,
    StagesShape,
    StressShape,
)

__all__ = [
    # User scenarios
    "BrowserUser",
    "BorrowerUser",
    "LibrarianUser",
    "PatronManagerUser",
    "StressTestUser",
    # Load shapes
    "StagesShape",
    "SpikeShape",
    "SoakShape",
    "StressShape",
    "CircuitBreakerTestShape",
]
