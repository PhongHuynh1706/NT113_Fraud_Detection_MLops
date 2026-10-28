
from unittest.mock import Mock

import numpy as np

from fraud_detection.training.preprocess import (
    NUMERIC_FEATURES,
)
from fraud_detection.serving.predictor import FraudPredictor


def test_predict_fraud(sample_transaction):
    predictor = FraudPredictor.__new__(FraudPredictor)

    predictor.model = Mock()
    predictor.model.predict_proba.return_value = np.array([
        [0.05, 0.95]
    ])

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
    predictor.model.predict_proba.return_value = np.array([
        [0.9, 0.1]
    ])

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
