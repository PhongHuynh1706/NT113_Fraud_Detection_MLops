from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from fraud_detection.serving.main import app
from fraud_detection.serving.model_loader import get_predictor


@pytest.fixture
def fake_predictor():
    predictor = Mock()
    predictor.model_name = 'fraud-detection'
    predictor.model_version = '1'
    predictor.predict.return_value = {
        'prediction': 0,
        'fraud_probability': 0.1,
        'threshold': 0.8,
        'model_name': 'fraud-detection',
        'model_version': '1',
    }
    return predictor


@pytest.fixture
def client(fake_predictor):
    # No lifespan context: unit tests must not connect to MLflow.
    app.dependency_overrides[get_predictor] = lambda: fake_predictor
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_liveness_without_model():
    response = TestClient(app).get('/health/live')
    assert response.status_code == 200
    assert response.json() == {'status': 'alive'}


def test_readiness(client):
    response = client.get('/health/ready')
    assert response.status_code == 200
    assert response.json() == {
        'status': 'ready',
        'model_name': 'fraud-detection',
        'model_version': '1',
    }


def test_readiness_without_model():
    app.dependency_overrides.clear()
    app.state.predictor = None
    response = TestClient(app).get('/health/ready')
    assert response.status_code == 503
    assert response.json()['detail'] == 'Model not ready'


def test_predict_legitimate(client, fake_predictor, sample_transaction):
    response = client.post('/predict', json=sample_transaction)
    assert response.status_code == 200
    assert response.json()['prediction'] == 0
    fake_predictor.predict.assert_called_once_with(sample_transaction)


def test_predict_fraud(client, fake_predictor, sample_transaction):
    fake_predictor.predict.return_value['prediction'] = 1
    fake_predictor.predict.return_value['fraud_probability'] = 0.95
    response = client.post('/predict', json=sample_transaction)
    assert response.status_code == 200
    assert response.json()['prediction'] == 1


def test_predict_invalid_payload(client):
    response = client.post('/predict', json={'unexpected': 123})
    assert response.status_code == 422


def test_predict_internal_error(client, fake_predictor, sample_transaction):
    fake_predictor.predict.side_effect = RuntimeError('private error')
    response = client.post('/predict', json=sample_transaction)
    assert response.status_code == 500
    assert response.json() == {'detail': 'Prediction failed'}
    assert 'private error' not in response.text


def test_predict_without_model(sample_transaction):
    app.dependency_overrides.clear()
    app.state.predictor = None
    response = TestClient(app).post('/predict', json=sample_transaction)
    assert response.status_code == 503


def test_metrics_endpoint():
    response = TestClient(app).get('/metrics')
    assert response.status_code == 200
    assert 'text/plain' in response.headers['content-type']
    assert 'fraud_prediction_requests_total' in response.text
    assert 'fraud_prediction_duration_seconds' in response.text
    assert 'fraud_prediction_positive_total' in response.text
