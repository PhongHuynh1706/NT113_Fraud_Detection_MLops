
import numpy as np
import pandas as pd
import pytest

from fraud_detection.training.preprocess import (
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    transform_features,
)


def test_transform_features(sample_transaction):
    preprocessing = {
        "numeric_medians": {
            column: 10.0
            for column in NUMERIC_FEATURES
        }
    }

    df = pd.DataFrame([sample_transaction])

    result = transform_features(
        df,
        preprocessing,
    )

    assert list(result.columns) == FEATURE_COLUMNS
    assert result.shape == (1, 35)


def test_numeric_missing_value(sample_transaction):
    sample_transaction["transaction_amount"] = np.nan

    preprocessing = {
        "numeric_medians": {
            column: 10.0
            for column in NUMERIC_FEATURES
        }
    }

    result = transform_features(
        pd.DataFrame([sample_transaction]),
        preprocessing,
    )

    assert result["transaction_amount"].iloc[0] == 10.0


def test_invalid_binary_value(sample_transaction):
    sample_transaction["card_present"] = 5

    preprocessing = {
        "numeric_medians": {
            column: 10.0
            for column in NUMERIC_FEATURES
        }
    }

    with pytest.raises(
        ValueError,
        match="Invalid binary feature",
    ):
        transform_features(
            pd.DataFrame([sample_transaction]),
            preprocessing,
        )
