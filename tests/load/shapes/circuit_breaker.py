"""
Circuit breaker test pattern for resilience testing.
"""
from locust import LoadTestShape


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
