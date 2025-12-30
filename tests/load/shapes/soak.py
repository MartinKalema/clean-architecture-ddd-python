"""
Soak test pattern for long-duration testing.
"""
import math

from locust import LoadTestShape


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
