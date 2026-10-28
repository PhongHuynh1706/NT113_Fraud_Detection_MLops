
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    precision_recall_curve
)


def find_best_threshold(y_true, probabilities):
    precision, recall, thresholds = (
        precision_recall_curve(
            y_true, probabilities
        )
    )

    if len(thresholds) == 0:
        raise ValueError("No valid thresholds")

    f1_scores = (
        2 * precision[:-1] * recall[:-1]
        / (
            precision[:-1]
            + recall[:-1]
            + 1e-12
        )
    )

    best_index = int(np.argmax(f1_scores))

    return float(thresholds[best_index])


def evaluate_model(y_true, probabilities, threshold):
    predictions = (
        probabilities >= threshold
    ).astype(int)

    tn, fp, fn, tp = confusion_matrix(
        y_true,
        predictions,
        labels=[0, 1]
    ).ravel()

    return {
        "pr_auc": float(
            average_precision_score(
                y_true, probabilities
            )
        ),
        "roc_auc": float(
            roc_auc_score(
                y_true, probabilities
            )
        ),
        "precision": float(
            precision_score(
                y_true, predictions,
                zero_division=0
            )
        ),
        "recall": float(
            recall_score(
                y_true, predictions,
                zero_division=0
            )
        ),
        "f1": float(
            f1_score(
                y_true, predictions,
                zero_division=0
            )
        ),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn)
    }


def evaluate_at_threshold(y_true, y_proba, threshold: float) -> dict:
    """Evaluate binary classification at a fixed threshold."""
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("Threshold must be between 0 and 1.")

    y_true = np.asarray(y_true).ravel()
    y_proba = np.asarray(y_proba).ravel()

    if len(y_true) != len(y_proba):
        raise ValueError("y_true and y_proba must have equal lengths.")

    y_pred = (y_proba >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(
        y_true, y_pred, labels=[0, 1]
    ).ravel()

    return {
        "threshold": float(threshold),
        "precision": float(
            precision_score(y_true, y_pred, zero_division=0)
        ),
        "recall": float(
            recall_score(y_true, y_pred, zero_division=0)
        ),
        "f1": float(
            f1_score(y_true, y_pred, zero_division=0)
        ),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
    }


def compare_validation_thresholds(
    y_val,
    val_proba,
    thresholds=(0.80, 0.824419525953317),
) -> pd.DataFrame:
    """Compare thresholds using validation predictions only."""
    results = [
        evaluate_at_threshold(y_val, val_proba, threshold)
        for threshold in thresholds
    ]

    return pd.DataFrame(results).sort_values(
        by="threshold"
    ).reset_index(drop=True)
