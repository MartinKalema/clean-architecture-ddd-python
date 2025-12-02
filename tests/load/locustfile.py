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
import math

from locust import LoadTestShape

# Import all user scenarios - Locust auto-discovers HttpUser subclasses
from tests.load.scenarios import (
    BorrowerUser,
    BrowserUser,
    LibrarianUser,
    StressTestUser,
)

# Re-export for Locust discovery
__all__ = ["BrowserUser", "BorrowerUser", "LibrarianUser", "StressTestUser"]


class StagesShape(LoadTestShape):
    """
    Multi-stage load pattern: ramp up -> steady -> ramp down.

    Mimics realistic traffic patterns with gradual changes.
    """

    stages = [
        {"duration": 60, "users": 50, "spawn_rate": 5},     # Warm up
        {"duration": 180, "users": 100, "spawn_rate": 10},  # Ramp up
        {"duration": 300, "users": 100, "spawn_rate": 10},  # Steady state
        {"duration": 60, "users": 50, "spawn_rate": 5},     # Ramp down
        {"duration": 30, "users": 10, "spawn_rate": 2},     # Cool down
    ]

    def tick(self):
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
            run_time -= stage["duration"]

        return None  # Stop test


class SpikeShape(LoadTestShape):
    """
    Spike test pattern: sudden burst of traffic.

    Tests how the system handles sudden load increases (e.g., flash sales).
    """

    # Time in seconds -> (users, spawn_rate)
    def tick(self):
        run_time = self.get_run_time()

        if run_time < 30:
            # Baseline
            return (20, 5)
        elif run_time < 60:
            # SPIKE! Sudden 10x increase
            return (200, 50)
        elif run_time < 120:
            # Sustained high load
            return (200, 10)
        elif run_time < 150:
            # Another spike
            return (500, 100)
        elif run_time < 210:
            # Recovery
            return (100, 10)
        elif run_time < 240:
            # Back to baseline
            return (20, 5)
        else:
            return None


class SoakShape(LoadTestShape):
    """
    Soak test pattern: sustained load over long period.

    Tests for memory leaks, connection pool exhaustion, etc.
    """

    def tick(self):
        run_time = self.get_run_time()

        if run_time < 60:
            # Ramp up
            users = min(100, int(run_time * 2))
            return (users, 5)
        elif run_time < 3600:  # 1 hour
            # Steady state with slight variations
            base_users = 100
            variation = int(20 * math.sin(run_time / 60))
            return (base_users + variation, 2)
        else:
            return None


class StressShape(LoadTestShape):
    """
    Stress test pattern: gradually increase until breaking point.

    Finds the system's capacity limits.
    """

    def tick(self):
        run_time = self.get_run_time()

        if run_time > 600:  # 10 minutes max
            return None

        # Increase users every 30 seconds
        stage = int(run_time / 30)
        users = 50 + (stage * 50)  # 50, 100, 150, 200...
        spawn_rate = 10 + (stage * 5)

        return (min(users, 1000), min(spawn_rate, 100))


class CircuitBreakerTestShape(LoadTestShape):
    """
    Pattern designed to trigger and test circuit breakers.

    Creates conditions that should open circuit breakers,
    then backs off to allow recovery.
    """

    def tick(self):
        run_time = self.get_run_time()

        if run_time < 30:
            # Normal load
            return (50, 10)
        elif run_time < 60:
            # Overwhelming spike to trigger circuit breakers
            return (500, 100)
        elif run_time < 120:
            # Back off - circuit breakers should be open
            return (20, 5)
        elif run_time < 180:
            # Gradual increase - test half-open state
            return (50, 10)
        elif run_time < 240:
            # Normal load - circuit breakers should close
            return (100, 10)
        else:
            return None
