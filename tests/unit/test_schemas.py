import pytest
from pydantic import ValidationError

from fraud_detection.serving.schemas import PredictionResponse, TransactionRequest
from fraud_detection.training.preprocess import (
    BINARY_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
)


def test_transaction_valid(sample_transaction):
    transaction = TransactionRequest.model_validate(sample_transaction)
    assert transaction.model_dump() == sample_transaction


def test_transaction_rejects_missing_required_field(sample_transaction):
    payload = sample_transaction.copy()
    payload.pop(next(iter(NUMERIC_FEATURES)))
    with pytest.raises(ValidationError):
        TransactionRequest.model_validate(payload)


def test_transaction_rejects_extra_field(sample_transaction):
    with pytest.raises(ValidationError):
        TransactionRequest.model_validate({**sample_transaction, 'unexpected': 123})


@pytest.mark.parametrize('invalid', [2, -1, 0.5, 'invalid'])
def test_transaction_rejects_invalid_binary(sample_transaction, invalid):
    if not BINARY_FEATURES:
        pytest.skip('No binary features configured')
    payload = sample_transaction.copy()
    payload[next(iter(BINARY_FEATURES))] = invalid
    with pytest.raises(ValidationError):
        TransactionRequest.model_validate(payload)


def test_transaction_accepts_nullable_fields(sample_transaction):
    payload = sample_transaction.copy()
    for name in [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES, *BINARY_FEATURES]:
        payload[name] = None
    transaction = TransactionRequest.model_validate(payload)
    assert all(value is None for value in transaction.model_dump().values())


def test_prediction_response_valid():
    response = PredictionResponse(
        prediction=1, fraud_probability=0.95, threshold=0.8,
        model_name='fraud-detection', model_version='1',
    )
    assert response.prediction == 1
    assert response.fraud_probability == 0.95


def test_prediction_response_rejects_invalid_prediction():
    with pytest.raises(ValidationError):
        PredictionResponse(
            prediction=2, fraud_probability=0.95, threshold=0.8,
            model_name='fraud-detection', model_version='1',
        )
