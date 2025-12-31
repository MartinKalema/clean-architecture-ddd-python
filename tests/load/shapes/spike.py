"""
Spike test pattern for sudden traffic bursts.
"""
from locust import LoadTestShape


class SpikeShape(LoadTestShape):
    """
    Spike test pattern: sudden burst of traffic.

    Tests how the system handles sudden load increases (e.g., flash sales).
    Designed for 10k user peaks.
    """

    def tick(self):
        run_time = self.get_run_time()

        if run_time < 30:
            # Baseline
            return (1000, 100)
        elif run_time < 60:
            # SPIKE! Sudden 10x increase
            return (10000, 500)
        elif run_time < 120:
            # Sustained high load
            return (10000, 200)
        elif run_time < 150:
            # Drop and spike again
            return (2000, 300)
        elif run_time < 180:
            # Second spike
            return (10000, 500)
        elif run_time < 210:
            # Recovery
            return (5000, 200)
        elif run_time < 240:
            # Back to baseline
            return (1000, 100)
        else:
            return None
