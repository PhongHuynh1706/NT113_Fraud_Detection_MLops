import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fraud_detection.api import create_app
from fraud_detection.model import ModelManifest, ModelRuntime


class SyntheticPredictor:
    """Test double only; this is not a trained fraud detection model."""

    def predict(self, data):
        assert list(data.columns) == ["synthetic_a", "synthetic_b"]
        return pd.DataFrame({"fraud_probability": [0.7] * len(data)})


@pytest.fixture
def runtime():
    manifest = ModelManifest(
        model_uri="unused",
        model_version="test-only",
        features=["synthetic_a", "synthetic_b"],
        threshold=0.7,
    )
    return ModelRuntime(manifest, SyntheticPredictor())


def test_missing_model_is_live_but_not_ready(monkeypatch):
    monkeypatch.delenv("MODEL_MANIFEST", raising=False)
    with TestClient(create_app()) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert client.post("/predict", json={"instances": [{"x": 1}]}).status_code == 503
        assert "fraud_model_ready 0.0" in client.get("/metrics").text


def test_prediction_threshold_and_order(runtime):
    with TestClient(create_app(lambda: runtime)) as client:
        assert client.get("/health/ready").status_code == 200
        response = client.post(
            "/predict",
            json={
                "instances": [
                    {"synthetic_b": 2, "synthetic_a": 1},
                    {"synthetic_a": 3, "synthetic_b": 4},
                ]
            },
        )
        assert response.status_code == 200
        assert response.json() == {
            "model_version": "test-only",
            "threshold": 0.7,
            "predictions": [{"fraud_probability": 0.7, "is_fraud": True}] * 2,
        }
        metrics = client.get("/metrics").text
        assert 'fraud_predictions_total{decision="fraud"} 2.0' in metrics
        assert 'route="/predict",status="200"' in metrics


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"synthetic_a": 1}],
        [{"synthetic_a": 1, "synthetic_b": 2, "extra": 3}],
        [{"synthetic_a": "1", "synthetic_b": 2}],
        [{"synthetic_a": True, "synthetic_b": 2}],
        [{"synthetic_a": None, "synthetic_b": 2}],
        [{"synthetic_a": 1, "synthetic_b": 2}] * 257,
    ],
)
def test_reject_invalid_input(runtime, rows):
    with TestClient(create_app(lambda: runtime)) as client:
        assert client.post("/predict", json={"instances": rows}).status_code == 422


def test_startup_failure_does_not_leak_secrets():
    def fail():
        raise RuntimeError("secret-token")

    with TestClient(create_app(fail)) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert "secret-token" not in response.text


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1, "0.7", True])
def test_reject_invalid_model_output(runtime, value):
    class BrokenPredictor:
        def predict(self, data):
            return pd.DataFrame({"fraud_probability": [value]})

    runtime.predictor = BrokenPredictor()
    with TestClient(create_app(lambda: runtime)) as client:
        response = client.post(
            "/predict", json={"instances": [{"synthetic_a": 1, "synthetic_b": 2}]}
        )
        assert response.status_code == 500


def test_unmatched_paths_use_bounded_metric_labels(runtime):
    with TestClient(create_app(lambda: runtime)) as client:
        client.get("/private-transaction-123")
        metrics = client.get("/metrics").text
        assert 'route="unmatched"' in metrics
        assert "private-transaction-123" not in metrics


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_returns_422(runtime, value):
    with TestClient(create_app(lambda: runtime)) as client:
        response = client.post(
            "/predict",
            content=('{"instances":[{"synthetic_a":' + value + ',"synthetic_b":2}]}'),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


def test_predictor_value_error_is_server_failure(runtime):
    class BrokenPredictor:
        def predict(self, data):
            raise ValueError("internal failure with sensitive detail")

    runtime.predictor = BrokenPredictor()
    with TestClient(create_app(lambda: runtime)) as client:
        response = client.post(
            "/predict", json={"instances": [{"synthetic_a": 1, "synthetic_b": 2}]}
        )
        assert response.status_code == 500
        assert "sensitive" not in response.text
