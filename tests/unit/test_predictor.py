
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from fraud_detection.training.preprocess import (
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
)
from fraud_detection.serving.predictor import FraudPredictor


@pytest.fixture
def predictor():
    """Create a predictor without loading MLflow model."""
    instance = FraudPredictor.__new__(FraudPredictor)

    instance.model = Mock()
    instance.preprocessing = {
        "numeric_medians": {
            column: 10.0
            for column in NUMERIC_FEATURES
        }
    }

    instance.threshold = 0.8
    instance.model_name = "fraud-detection"
    instance.model_version = "1"

    return instance


def test_predict_fraud(sample_transaction):
    predictor = FraudPredictor.__new__(FraudPredictor)

    predictor.model = Mock()
    predictor.model.predict.return_value = np.array([0.95])

    predictor.preprocessing = {
        "numeric_medians": {
            column: 10.0
            for column in NUMERIC_FEATURES
        }
    }

    predictor.threshold = 0.8
    predictor.model_name = "fraud-detection"
    predictor.model_version = "1"

    result = predictor.predict(sample_transaction)

    assert result["prediction"] == 1
    assert result["fraud_probability"] == 0.95
    assert result["threshold"] == 0.8


def test_predict_legitimate(sample_transaction):
    predictor = FraudPredictor.__new__(FraudPredictor)

    predictor.model = Mock()
    predictor.model.predict.return_value = np.array([0.1])

    predictor.preprocessing = {
        "numeric_medians": {
            column: 10.0
            for column in NUMERIC_FEATURES
        }
    }

    predictor.threshold = 0.8
    predictor.model_name = "fraud-detection"
    predictor.model_version = "1"

    result = predictor.predict(sample_transaction)

    assert result["prediction"] == 0
    assert result["fraud_probability"] == 0.1


@pytest.mark.parametrize(
    ("probability", "expected_prediction"),
    [
        (0.0, 0),
        (0.5, 0),
        (0.7999, 0),
        (0.8, 1),
        (0.8001, 1),
        (1.0, 1),
    ],
)
def test_prediction_threshold_boundary(
    predictor,
    sample_transaction,
    probability,
    expected_prediction,
):
    """Verify fraud classification around the threshold."""
    predictor.model.predict.return_value = np.array(
        [probability]
    )

    result = predictor.predict(sample_transaction)

    assert result["prediction"] == expected_prediction
    assert result["fraud_probability"] == pytest.approx(
        probability
    )
    assert result["threshold"] == 0.8


def test_prediction_response_fields(
    predictor,
    sample_transaction,
):
    """Verify prediction response structure."""
    predictor.model.predict.return_value = np.array([0.9])

    result = predictor.predict(sample_transaction)

    assert set(result.keys()) == {
        "prediction",
        "fraud_probability",
        "threshold",
        "model_name",
        "model_version",
    }

    assert result["prediction"] == 1
    assert result["model_name"] == "fraud-detection"
    assert result["model_version"] == "1"


def test_model_predict_called_once(
    predictor,
    sample_transaction,
):
    """Verify model inference is executed exactly once."""
    predictor.model.predict.return_value = np.array([0.7])

    predictor.predict(sample_transaction)

    predictor.model.predict.assert_called_once()


def test_model_receives_dataframe(
    predictor,
    sample_transaction,
):
    """Verify model input is a pandas DataFrame."""
    predictor.model.predict.return_value = np.array([0.7])

    predictor.predict(sample_transaction)

    args, kwargs = predictor.model.predict.call_args

    assert len(args) == 1
    assert kwargs == {}
    assert isinstance(args[0], pd.DataFrame)
    assert len(args[0]) == 1


def test_prediction_uses_feature_columns(
    predictor,
    sample_transaction,
    monkeypatch,
):
    """Verify predictor builds input with expected features."""
    captured = {}

    def fake_transform(df, preprocessing):
        captured["df"] = df.copy()
        captured["preprocessing"] = preprocessing
        return df

    monkeypatch.setattr(
        "fraud_detection.serving.predictor.transform_features",
        fake_transform,
    )

    predictor.model.predict.return_value = np.array([0.7])

    predictor.predict(sample_transaction)

    assert list(captured["df"].columns) == list(
        FEATURE_COLUMNS
    )
    assert captured["preprocessing"] is predictor.preprocessing


def test_model_inference_error(
    predictor,
    sample_transaction,
):
    """Verify model inference exceptions are propagated."""
    predictor.model.predict.side_effect = RuntimeError(
        "Model inference failed"
    )

    with pytest.raises(
        RuntimeError,
        match="Model inference failed",
    ):
        predictor.predict(sample_transaction)


def test_empty_model_prediction(
    predictor,
    sample_transaction,
):
    """Verify behavior when model returns no probabilities."""
    predictor.model.predict.return_value = np.array([])

    with pytest.raises(IndexError):
        predictor.predict(sample_transaction)


def test_invalid_model_prediction_value(
    predictor,
    sample_transaction,
):
    """Verify behavior when model returns a nonnumeric value."""
    predictor.model.predict.return_value = np.array(
        ["invalid"]
    )

    with pytest.raises(ValueError):
        predictor.predict(sample_transaction)
