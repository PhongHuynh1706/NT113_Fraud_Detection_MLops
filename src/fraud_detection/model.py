"""Load an explicitly configured, trusted MLflow probability model."""

import json
import math
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    model_uri: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    features: list[str] = Field(min_length=1)
    threshold: float = Field(ge=0, le=1)
    probability_column: str = "fraud_probability"

    @field_validator("features")
    @classmethod
    def validate_features(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values) or len(values) != len(set(values)):
            raise ValueError("Feature names must be nonempty and unique")
        return values


class Predictor(Protocol):
    def predict(self, data: pd.DataFrame) -> Any: ...


class FeatureMismatch(ValueError):
    """Request features do not match the model contract."""


class ModelRuntime:
    def __init__(self, manifest: ModelManifest, predictor: Predictor):
        self.manifest = manifest
        self.predictor = predictor

    @classmethod
    def load(cls, path: str) -> "ModelRuntime":
        import mlflow.pyfunc

        manifest = ModelManifest.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
        predictor = mlflow.pyfunc.load_model(manifest.model_uri)
        return cls(manifest, predictor)

    def predict(self, rows: list[dict[str, float | int]]) -> list[float]:
        expected = set(self.manifest.features)
        if any(set(row) != expected for row in rows):
            raise FeatureMismatch("Each row must contain exactly the configured feature names")
        frame = pd.DataFrame(rows, columns=self.manifest.features, dtype="float64")
        output = self.predictor.predict(frame)
        column = self.manifest.probability_column
        if not isinstance(output, pd.DataFrame) or column not in output.columns:
            raise RuntimeError("Model must return a DataFrame with a probability column")
        if len(output) != len(rows):
            raise RuntimeError("Model returned an invalid number of predictions")
        values = output[column].tolist()
        # Reject strings, booleans, nonfinite values, and out-of-range scores.
        if any(
            isinstance(value, (bool, str))
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 1
            for value in values
        ):
            raise RuntimeError("Model returned invalid probabilities")
        return [float(value) for value in values]
