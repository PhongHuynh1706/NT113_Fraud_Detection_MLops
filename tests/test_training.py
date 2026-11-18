import numpy as np
import pandas as pd
import pytest

from fraud_detection.train import chronological_split, evaluate, select_threshold


def test_time_boundaries_keep_equal_timestamps_together():
    data = pd.DataFrame(
        {
            "transaction_datetime": np.repeat(pd.date_range("2025-01-01", periods=20), 2),
            "is_fraud": [0, 1] * 20,
        }
    ).sample(frac=1, random_state=42)
    train, validation, test = chronological_split(data, "transaction_datetime")
    assert train.transaction_datetime.max() < validation.transaction_datetime.min()
    assert validation.transaction_datetime.max() < test.transaction_datetime.min()
    assert len(train) + len(validation) + len(test) == len(data)
    assert not set(train.index) & set(test.index)


def test_threshold_optimizes_validation_f1():
    labels = np.array([0, 0, 1, 1])
    scores = np.array([0.01, 0.2, 0.3, 0.4])
    threshold = select_threshold(labels, scores)
    assert threshold == 0.3
    assert evaluate(labels, scores, threshold)["f1"] == 1.0


def test_split_rejects_single_class_partition():
    data = pd.DataFrame(
        {"transaction_datetime": pd.date_range("2025-01-01", periods=20), "is_fraud": [0] * 20}
    )
    with pytest.raises(ValueError, match="both classes"):
        chronological_split(data, "transaction_datetime")
