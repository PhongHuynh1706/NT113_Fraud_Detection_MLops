
import json
import os
import tempfile

import mlflow
import mlflow.pyfunc
import numpy as np

from mlflow.models import infer_signature


class FraudModelWrapper(mlflow.pyfunc.PythonModel):
    """
    Unified MLflow inference wrapper.

    Supported algorithms:
    - CatBoost
    - LightGBM
    - XGBoost

    Output:
        Probability of fraud (class 1).
    """

    def __init__(self, model):
        self.model = model

    def predict(self, context, model_input, params=None):
        probabilities = self.model.predict_proba(
            model_input
        )

        return np.asarray(probabilities)[:, 1]


def log_training_info(
    model_config,
    train_samples,
    val_samples,
    test_samples,
    feature_count,
):
    params = model_config.copy()
    algorithm = params.pop("algorithm")

    mlflow.set_tags({
        "project": "fraud-detection-mlops",
        "algorithm": algorithm,
        "stage": "training",
    })

    mlflow.log_params(params)

    mlflow.log_params({
        "train_samples": train_samples,
        "validation_samples": val_samples,
        "test_samples": test_samples,
        "feature_count": feature_count,
    })


def log_threshold_analysis(
    custom_threshold,
    comparison,
    custom_metrics,
):
    mlflow.log_metric(
        "custom_threshold",
        float(custom_threshold),
    )

    mlflow.log_table(
        comparison,
        artifact_file=(
            "evaluation/"
            "validation_threshold_comparison.json"
        ),
    )

    mlflow.log_metrics({
        f"val_custom_{key}": float(custom_metrics[key])
        for key in (
            "precision",
            "recall",
            "f1",
            "tp",
            "fp",
            "tn",
            "fn",
        )
    })


def log_evaluation(
    threshold,
    val_metrics,
    test_metrics,
):
    mlflow.log_metric(
        "decision_threshold",
        float(threshold),
    )

    mlflow.log_metrics({
        f"val_{key}": float(value)
        for key, value in val_metrics.items()
    })

    mlflow.log_metrics({
        f"test_{key}": float(value)
        for key, value in test_metrics.items()
    })


def log_inference_artifacts(
    preprocessing,
    threshold,
):
    with tempfile.TemporaryDirectory() as tmp:
        preprocessing_path = os.path.join(
            tmp,
            "preprocessing.json",
        )

        threshold_path = os.path.join(
            tmp,
            "threshold.json",
        )

        with open(
            preprocessing_path,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(preprocessing, f)

        with open(
            threshold_path,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                {"threshold": float(threshold)},
                f,
            )

        mlflow.log_artifacts(
            tmp,
            artifact_path="inference_config",
        )


def log_model(model, algorithm, input_example):
    algorithm = algorithm.lower()

    supported_algorithms = (
        "catboost",
        "lightgbm",
        "xgboost",
    )

    if algorithm not in supported_algorithms:
        raise ValueError(
            f"Unsupported algorithm: {algorithm}"
        )

    mlflow.set_tag(
        "model_algorithm",
        algorithm,
    )

    wrapper = FraudModelWrapper(model)

    output_example = wrapper.predict(
        context=None,
        model_input=input_example,
    )

    signature = infer_signature(
        input_example,
        output_example,
    )

    return mlflow.pyfunc.log_model(
        name="model",
        python_model=wrapper,
        input_example=input_example,
        signature=signature,
        code_paths=["src"],
        pip_requirements=[
            "mlflow",
            "numpy",
            "pandas",
            "scikit-learn",
            "catboost",
            "lightgbm",
            "xgboost",
        ],
    )
