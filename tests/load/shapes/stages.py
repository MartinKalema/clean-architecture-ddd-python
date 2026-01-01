"""
Multi-stage load pattern for realistic traffic simulation.
"""
from locust import LoadTestShape


class StagesShape(LoadTestShape):
    """
    Multi-stage load pattern: ramp up -> steady -> ramp down.

    Mimics realistic traffic patterns with gradual changes.
    Designed for 2k user load testing.
    """

    stages = [
        {"duration": 10, "users": 300, "spawn_rate": 50},      # Quick warm up
        {"duration": 20, "users": 1500, "spawn_rate": 100},    # Ramp to 1.5k
        {"duration": 30, "users": 3000, "spawn_rate": 100},    # Ramp to 3k
        {"duration": 60, "users": 3000, "spawn_rate": 100},    # Steady at 3k
        {"duration": 20, "users": 1500, "spawn_rate": 50},     # Ramp down
        {"duration": 10, "users": 300, "spawn_rate": 50},      # Cool down
    ]

    def tick(self):
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
            run_time -= stage["duration"]

        return None
