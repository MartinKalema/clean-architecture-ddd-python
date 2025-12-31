"""
Load Test Suite - Manual mode (no shapes).

Usage:
    # Manual user control
    uv run locust -f tests/load/run_manual.py --headless -u 10000 -r 500 -t 1m --host http://localhost:8000

    # Web UI
    uv run locust -f tests/load/run_manual.py --host http://localhost:8000

For shape tests, use:
    - run_stages.py      (ramp to 10k)
    - run_spike.py       (traffic bursts)
    - run_stress.py      (find breaking point)
    - run_circuit_breaker.py (test resilience)
    - run_soak.py        (sustained 10k for 1 hour)
"""
from scenarios import (
    BorrowerUser,
    BrowserUser,
    LibrarianUser,
    PatronManagerUser,
    StressTestUser,
)

__all__ = [
    "BrowserUser",
    "BorrowerUser",
    "LibrarianUser",
    "PatronManagerUser",
    "StressTestUser",
]
