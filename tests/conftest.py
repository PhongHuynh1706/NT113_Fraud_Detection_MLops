
import pytest

from fraud_detection.training.preprocess import (
    NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
    BINARY_FEATURES,
)


@pytest.fixture
def sample_transaction():
    data = {}

    for column in NUMERIC_FEATURES:
        data[column] = 1.0

    for column in CATEGORICAL_FEATURES:
        data[column] = "Unknown"

    for column in BINARY_FEATURES:
        data[column] = 0

    return data
