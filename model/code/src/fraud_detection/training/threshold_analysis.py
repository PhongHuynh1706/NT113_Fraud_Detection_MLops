
import numpy as np

from fraud_detection.training.evaluate import (
    find_best_threshold,
    compare_validation_thresholds,
)


def analyze_thresholds(
    y_val,
    val_probabilities,
    custom_threshold=0.80,
):
    if not 0.0 <= custom_threshold <= 1.0:
        raise ValueError("Threshold must be between 0 and 1")

    best_threshold = float(
        find_best_threshold(y_val, val_probabilities)
    )

    comparison = compare_validation_thresholds(
        y_val,
        val_probabilities,
        thresholds=[custom_threshold, best_threshold],
    )

    print("\n=== VALIDATION THRESHOLD COMPARISON ===")
    print(comparison.to_string(index=False))

    custom_metrics = comparison.loc[
        np.isclose(
            comparison["threshold"].to_numpy(),
            custom_threshold,
        )
    ].iloc[0].to_dict()

    return best_threshold, comparison, custom_metrics
