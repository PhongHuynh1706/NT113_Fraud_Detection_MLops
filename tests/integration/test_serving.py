
from unittest.mock import Mock

from fastapi.testclient import TestClient

from fraud_detection.serving.main import app
from fraud_detection.serving.model_loader import get_predictor


def test_predict_endpoint(sample_transaction):
    fake_predictor = Mock()

    fake_predictor.predict.return_value = {
        "prediction": 1,
        "fraud_probability": 0.95,
        "threshold": 0.8,
        "model_name": "fraud-detection",
        "model_version": "1",
    }

    app.dependency_overrides[get_predictor] = (
        lambda: fake_predictor
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/predict",
                json=sample_transaction,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["prediction"] == 1

    fake_predictor.predict.assert_called_once()
