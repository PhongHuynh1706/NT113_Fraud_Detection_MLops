
from typing import Literal

from pydantic import BaseModel, ConfigDict, create_model

from fraud_detection.training.preprocess import (
    NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
    BINARY_FEATURES,
)


fields = {}

for name in NUMERIC_FEATURES:
    fields[name] = (float | None, ...)

for name in CATEGORICAL_FEATURES:
    fields[name] = (str | None, ...)

for name in BINARY_FEATURES:
    fields[name] = (Literal[0, 1] | None, ...)


TransactionRequest = create_model(
    "TransactionRequest",
    __config__=ConfigDict(extra="forbid"),
    **fields,
)


class PredictionResponse(BaseModel):
    prediction: Literal[0, 1]
    fraud_probability: float
    threshold: float
    model_name: str
    model_version: str
