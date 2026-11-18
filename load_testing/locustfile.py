"""Use an explicit synthetic payload matching your trained model's contract."""

import json
import os
import random
from pathlib import Path

from locust import HttpUser, between, task


class FraudUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        payload_path = os.environ.get("LOCUST_PAYLOAD_FILE")
        if not payload_path:
            raise RuntimeError("Set LOCUST_PAYLOAD_FILE to an approved synthetic JSON payload")
        self.payload = json.loads(Path(payload_path).read_text(encoding="utf-8-sig"))
        self.instances = self.payload.get("instances")
        if not isinstance(self.instances, list) or not self.instances:
            raise ValueError("Payload must contain a nonempty instances list")

    @task
    def predict(self):
        # The file is a pool: send one randomly selected transaction per request.
        payload = {"instances": [random.choice(self.instances)]}  # noqa: S311
        with self.client.post("/predict", json=payload, catch_response=True) as response:
            if response.status_code != 200:
                response.failure("Prediction request failed")
            else:
                try:
                    result = response.json()
                    if len(result["predictions"]) != 1:
                        response.failure("Prediction count mismatch")
                except (ValueError, KeyError, TypeError):
                    response.failure("Invalid prediction response")
