"""
Soak test pattern for long-duration testing.
"""
import math

from locust import LoadTestShape


class SoakShape(LoadTestShape):
    """
    Soak test pattern: sustained load over long period.

    Tests for memory leaks, connection pool exhaustion, etc.
    Maintains 10k users with slight variations for 1 hour.
    """

    def tick(self):
        run_time = self.get_run_time()

        if run_time < 60:
            # Ramp up to 10k
            users = min(10000, int(run_time * 200))
            return (users, 300)
        elif run_time < 3600:  # 1 hour
            # Steady state at 10k with slight variations
            base_users = 10000
            variation = int(1000 * math.sin(run_time / 60))
            return (base_users + variation, 100)
        else:
            return None
