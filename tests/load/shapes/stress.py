"""
Stress test pattern for finding system limits.
"""
from locust import LoadTestShape


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
