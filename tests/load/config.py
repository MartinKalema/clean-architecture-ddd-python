"""
Load Test Configuration and SLA Definitions.

Define performance targets and test parameters here.
These should be based on business requirements and production metrics.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SLAConfig:
    """Service Level Agreement configuration."""

    # Response time thresholds (milliseconds)
    p50_latency_ms: int = 100      # Median response time
    p95_latency_ms: int = 200      # 95th percentile
    p99_latency_ms: int = 500      # 99th percentile

    # Error rate threshold (percentage)
    max_error_rate: float = 1.0    # 1% max errors

    # Throughput (requests per second)
    min_rps: int = 100             # Minimum sustained RPS

    # Availability
    min_availability: float = 99.9  # 99.9% uptime


@dataclass(frozen=True)
class LoadProfile:
    """Load test profile configuration."""

    name: str
    users: int
    spawn_rate: int                 # Users per second
    run_time: str                   # e.g., "5m", "1h"

    # Optional ramp pattern
    ramp_up_time: Optional[str] = None
    ramp_down_time: Optional[str] = None


# Pre-defined load profiles
PROFILES = {
    "smoke": LoadProfile(
        name="smoke",
        users=10,
        spawn_rate=2,
        run_time="1m",
    ),
    "load": LoadProfile(
        name="load",
        users=100,
        spawn_rate=10,
        run_time="5m",
    ),
    "stress": LoadProfile(
        name="stress",
        users=500,
        spawn_rate=20,
        run_time="10m",
    ),
    "spike": LoadProfile(
        name="spike",
        users=1000,
        spawn_rate=100,  # Sudden spike
        run_time="5m",
    ),
    "soak": LoadProfile(
        name="soak",
        users=200,
        spawn_rate=10,
        run_time="1h",
    ),
}


# Test data configuration
TEST_DATA_PREFIX = "LOADTEST"  # Prefix for identifying test data
CLEANUP_AFTER_TEST = True      # Whether to clean up test data


# Endpoint weights (relative frequency)
ENDPOINT_WEIGHTS = {
    "list_books": 50,      # Most common - browsing
    "get_book": 30,        # View details
    "add_book": 5,         # Rare - admin action
    "borrow_book": 10,     # Moderate - user action
    "return_book": 5,      # Rare - after borrow
}


# Default SLA
DEFAULT_SLA = SLAConfig()
