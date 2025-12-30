"""
Multi-stage load pattern for realistic traffic simulation.
"""
from locust import LoadTestShape


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

        return None
