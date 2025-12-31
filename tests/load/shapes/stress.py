"""
Stress test pattern for finding system limits.
"""
from locust import LoadTestShape


class StressShape(LoadTestShape):
    """
    Stress test pattern: gradually increase until breaking point.

    Finds the system's capacity limits.
    Ramps up to 10k+ users to find the breaking point.
    """

    def tick(self):
        run_time = self.get_run_time()

        if run_time > 600:  # 10 minutes max
            return None

        # Increase users every 30 seconds
        stage = int(run_time / 30)
        users = 500 + (stage * 500)  # 500, 1000, 1500, 2000... up to 10k
        spawn_rate = 50 + (stage * 25)

        return (min(users, 10000), min(spawn_rate, 500))
