"""
Circuit breaker test pattern for resilience testing.
"""
from locust import LoadTestShape


class CircuitBreakerTestShape(LoadTestShape):
    """
    Pattern designed to trigger and test circuit breakers.

    Creates conditions that should open circuit breakers,
    then backs off to allow recovery.
    Uses 10k+ users to stress the system.
    """

    def tick(self):
        run_time = self.get_run_time()

        if run_time < 30:
            # Normal load
            return (2000, 200)
        elif run_time < 60:
            # Overwhelming spike to trigger circuit breakers
            return (15000, 500)
        elif run_time < 120:
            # Back off - circuit breakers should be open
            return (500, 50)
        elif run_time < 180:
            # Gradual increase - test half-open state
            return (2000, 100)
        elif run_time < 240:
            # Normal load - circuit breakers should close
            return (5000, 200)
        else:
            return None
