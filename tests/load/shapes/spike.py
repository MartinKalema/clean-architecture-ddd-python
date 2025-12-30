"""
Spike test pattern for sudden traffic bursts.
"""
from locust import LoadTestShape


class SpikeShape(LoadTestShape):
    """
    Spike test pattern: sudden burst of traffic.

    Tests how the system handles sudden load increases (e.g., flash sales).
    """

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
