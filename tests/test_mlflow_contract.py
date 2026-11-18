import json

import mlflow.pyfunc
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from mlflow.models import infer_signature
from pydantic import ValidationError

from fraud_detection.api import create_app
from fraud_detection.model import ModelManifest, ModelRuntime


class ContractOnlyModel(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input, params=None):
        return pd.DataFrame({"fraud_probability": [0.25] * len(model_input)})


def test_actual_mlflow_save_load_and_serve(tmp_path):
    sample = pd.DataFrame({"synthetic_feature": [1.0]})
    output = pd.DataFrame({"fraud_probability": [0.25]})
    model_path = tmp_path / "model"
    mlflow.pyfunc.save_model(
        path=str(model_path),
        python_model=ContractOnlyModel(),
        signature=infer_signature(sample, output),
        input_example=sample,
        pip_requirements=[],
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "model_uri": str(model_path),
                "model_version": "contract-test",
                "features": ["synthetic_feature"],
                "threshold": 0.5,
            }
        ),
        encoding="utf-8",
    )
    with TestClient(create_app(lambda: ModelRuntime.load(str(manifest_path)))) as client:
        # JSON integer inputs must be normalized to the model's double signature.
        response = client.post("/predict", json={"instances": [{"synthetic_feature": 1}]})
        assert response.status_code == 200
        assert response.json()["predictions"] == [{"fraud_probability": 0.25, "is_fraud": False}]


@pytest.mark.parametrize("features", [[], ["a", "a"], [""]])
def test_invalid_manifest(features):
    with pytest.raises(ValidationError):
        ModelManifest(model_uri="unused", model_version="test", features=features, threshold=0.5)
