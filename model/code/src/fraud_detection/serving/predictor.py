
import json
import os

import mlflow
import mlflow.pyfunc
import pandas as pd

from mlflow.tracking import MlflowClient

from fraud_detection.training.preprocess import (
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    transform_features,
)


class FraudPredictor:
    def __init__(self):
        tracking_uri = os.getenv(
            "MLFLOW_TRACKING_URI",
            "http://127.0.0.1:5000",
        )

        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_registry_uri(tracking_uri)

        self.model_name = os.getenv(
            "MODEL_NAME",
            "fraud-detection-model",
        )
        self.model_alias = os.getenv(
            "MODEL_ALIAS",
            "candidate",
        )

        client = MlflowClient()

        # Resolve alias thành model version cố định
        version_info = client.get_model_version_by_alias(
            self.model_name,
            self.model_alias,
        )

        self.model_version = str(version_info.version)

        model_uri = (
            f"models:/{self.model_name}/"
            f"{self.model_version}"
        )

        # Load model theo MLflow PyFunc
        # Hỗ trợ CatBoost, LightGBM và XGBoost
        self.model = mlflow.pyfunc.load_model(
            model_uri
        )

        # Xác định training run chứa preprocessing
        # và threshold artifacts
        run_id = version_info.run_id

        if not run_id:
            model_info = mlflow.models.get_model_info(
                model_uri
            )
            run_id = model_info.run_id

        if not run_id:
            raise RuntimeError(
                "Cannot determine training run ID. "
                "Store training_run_id as a model "
                "version tag during registration."
            )

        self.run_id = run_id

        # Load preprocessing từ training run
        preprocessing_path = client.download_artifacts(
            run_id,
            "inference_config/preprocessing.json",
        )

        with open(
            preprocessing_path,
            encoding="utf-8",
        ) as f:
            self.preprocessing = json.load(f)

        # Load threshold từ training run
        threshold_path = client.download_artifacts(
            run_id,
            "inference_config/threshold.json",
        )

        with open(
            threshold_path,
            encoding="utf-8",
        ) as f:
            threshold_config = json.load(f)

        self.threshold = float(
            threshold_config["threshold"]
        )

        if not 0 <= self.threshold <= 1:
            raise ValueError(
                "Invalid model threshold"
            )

        missing = (
            set(NUMERIC_FEATURES)
            - set(self.preprocessing["numeric_medians"])
        )

        if missing:
            raise ValueError(
                f"Missing preprocessing medians: {missing}"
            )

        print(
            f"Loaded {self.model_name} "
            f"version={self.model_version} "
            f"threshold={self.threshold}"
        )

    def predict(self, transaction: dict):
        df = pd.DataFrame(
            [transaction],
            columns=FEATURE_COLUMNS,
        )

        X = transform_features(
            df,
            self.preprocessing,
        )

        # MLflow PyFunc trả về xác suất fraud
        probabilities = self.model.predict(X)

        probability = float(
            probabilities[0]
        )

        prediction = int(
            probability >= self.threshold
        )

        return {
            "prediction": prediction,
            "fraud_probability": probability,
            "threshold": self.threshold,
            "model_name": self.model_name,
            "model_version": self.model_version,
        }
