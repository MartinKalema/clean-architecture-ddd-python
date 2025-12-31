"""
Multi-stage load pattern for realistic traffic simulation.
"""
from locust import LoadTestShape


class StagesShape(LoadTestShape):
    """
    Multi-stage load pattern: ramp up -> steady -> ramp down.

    Mimics realistic traffic patterns with gradual changes.
    Designed for 10k user load testing.
    """

    stages = [
        {"duration": 10, "users": 1000, "spawn_rate": 200},    # Quick warm up
        {"duration": 20, "users": 5000, "spawn_rate": 400},    # Ramp to 5k
        {"duration": 30, "users": 10000, "spawn_rate": 500},   # Ramp to 10k
        {"duration": 60, "users": 10000, "spawn_rate": 500},   # Steady at 10k
        {"duration": 20, "users": 5000, "spawn_rate": 300},    # Ramp down
        {"duration": 10, "users": 1000, "spawn_rate": 200},    # Cool down
    ]

    def tick(self):
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
            run_time -= stage["duration"]

        return None
