
import json
import os
from pathlib import Path

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
        self.model_source = os.getenv(
            "MODEL_SOURCE",
            "registry",
        ).lower()

        self.model_name = os.getenv(
            "MODEL_NAME",
            "fraud-detection-model",
        )

        self.model_alias = os.getenv(
            "MODEL_ALIAS",
            "candidate",
        )

        if self.model_source == "local":
            self._load_from_local()

        elif self.model_source == "registry":
            self._load_from_registry()

        else:
            raise ValueError(
                f"Unsupported MODEL_SOURCE: "
                f"{self.model_source}"
            )

        # Validate threshold
        if not 0 <= self.threshold <= 1:
            raise ValueError(
                "Invalid model threshold"
            )

        # Validate preprocessing
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
            f"source={self.model_source} "
            f"threshold={self.threshold}"
        )

    def _load_from_local(self):
        model_dir = Path(
            os.getenv(
                "MODEL_DIR",
                "/app/model",
            )
        )

        if not model_dir.is_dir():
            raise FileNotFoundError(
                f"Model directory not found: {model_dir}"
            )

        # Load MLflow PyFunc model
        self.model = mlflow.pyfunc.load_model(
            str(model_dir)
        )

        # Load preprocessing configuration
        preprocessing_path = (
            model_dir
            / "inference_config"
            / "preprocessing.json"
        )

        with preprocessing_path.open(
            "r",
            encoding="utf-8",
        ) as f:
            self.preprocessing = json.load(f)

        # Load threshold configuration
        threshold_path = (
            model_dir
            / "inference_config"
            / "threshold.json"
        )

        with threshold_path.open(
            "r",
            encoding="utf-8",
        ) as f:
            threshold_config = json.load(f)

        self.threshold = float(
            threshold_config["threshold"]
        )

        # Load version metadata exported with model
        metadata_path = (
            model_dir / "model_metadata.json"
        )

        if not metadata_path.is_file():
            raise FileNotFoundError(
                f"Model metadata not found: {metadata_path}"
            )

        with metadata_path.open(
            "r",
            encoding="utf-8",
        ) as f:
            metadata = json.load(f)

        self.model_name = metadata["model_name"]
        self.model_version = str(
            metadata["model_version"]
        )
        self.run_id = metadata.get("run_id")

    def _load_from_registry(self):
        tracking_uri = os.getenv(
            "MLFLOW_TRACKING_URI",
            "http://127.0.0.1:5000",
        )

        mlflow.set_tracking_uri(
            tracking_uri
        )

        mlflow.set_registry_uri(
            tracking_uri
        )

        client = MlflowClient()

        # Resolve alias to a fixed model version
        version_info = (
            client.get_model_version_by_alias(
                self.model_name,
                self.model_alias,
            )
        )

        self.model_version = str(
            version_info.version
        )

        model_uri = (
            f"models:/{self.model_name}/"
            f"{self.model_version}"
        )

        # Load MLflow PyFunc model
        self.model = mlflow.pyfunc.load_model(
            model_uri
        )

        # Resolve training run ID
        run_id = version_info.run_id

        if not run_id:
            model_info = (
                mlflow.models.get_model_info(
                    model_uri
                )
            )
            run_id = model_info.run_id

        if not run_id:
            raise RuntimeError(
                "Cannot determine training run ID. "
                "Store training_run_id as a model "
                "version tag during registration."
            )

        self.run_id = run_id

        # Download preprocessing artifact
        preprocessing_path = (
            client.download_artifacts(
                run_id,
                "inference_config/preprocessing.json",
            )
        )

        with open(
            preprocessing_path,
            encoding="utf-8",
        ) as f:
            self.preprocessing = json.load(f)

        # Download threshold artifact
        threshold_path = (
            client.download_artifacts(
                run_id,
                "inference_config/threshold.json",
            )
        )

        with open(
            threshold_path,
            encoding="utf-8",
        ) as f:
            threshold_config = json.load(f)

        self.threshold = float(
            threshold_config["threshold"]
        )

    def predict(self, transaction: dict):
        # Convert transaction to DataFrame
        df = pd.DataFrame(
            [transaction],
            columns=FEATURE_COLUMNS,
        )

        # Apply training preprocessing
        X = transform_features(
            df,
            self.preprocessing,
        )

        # MLflow PyFunc returns fraud probability
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
