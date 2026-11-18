import json
from pathlib import Path

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
import pytest

from fraud_detection.model import ModelRuntime
from fraud_detection.train import chronological_split, evaluate, select_threshold, train


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


@pytest.fixture
def synthetic_training(tmp_path):
    """Small deterministic dataset; all storage stays in pytest's temporary folder."""
    rng = np.random.default_rng(42)
    labels = np.tile([0, 1], 200)
    frame = pd.DataFrame(
        {
            "transaction_id": [f"synthetic-{i}" for i in range(400)],
            "customer_id": [f"synthetic-customer-{i % 20}" for i in range(400)],
            "transaction_datetime": pd.date_range("2025-01-01", periods=400, freq="h"),
            "is_fraud": labels,
            "signal": labels + rng.normal(0, 0.01, 400),
            "drift": np.linspace(0, 10, 400),
        }
    )
    dataset = tmp_path / "synthetic.csv"
    frame.to_csv(dataset, index=False)
    config = json.loads(Path("configs/training.json").read_text(encoding="utf-8"))
    config.update(
        dataset=str(dataset),
        features=["signal", "drift"],
        max_threads=1,
        experiment="synthetic-contract",
        registered_model="SyntheticTestOnly",
    )
    config["candidates"]["hist_gradient_boosting"].update(max_iter=5, min_samples_leaf=5)
    previous_tracking = mlflow.get_tracking_uri()
    previous_registry = mlflow.get_registry_uri()
    try:
        yield config, frame, tmp_path / "output"
    finally:
        mlflow.end_run()
        mlflow.set_tracking_uri(previous_tracking)
        mlflow.set_registry_uri(previous_registry)


def test_train_register_export_and_reload_without_preprocessing_leakage(synthetic_training):
    config, frame, output = synthetic_training
    report = train(config, output)
    assert report["acceptance_passed"] is True
    assert report["reload_verified"] is True
    assert report["model_version"] == "1"
    assert report["test"]["f1"] > report["baseline_test"]["f1"]
    assert sum(part["rows"] for part in report["splits"].values()) == len(frame)
    manifest = json.loads((output / "manifest.json").read_text())
    runtime = ModelRuntime.load(str(output / "manifest.json"))
    sample = frame[config["features"]].iloc[-10:].astype(float)
    exported = runtime.predict(sample.to_dict(orient="records"))
    registry = mlflow.pyfunc.load_model(report["model_uri"])
    np.testing.assert_allclose(exported, registry.predict(sample)["fraud_probability"])
    assert all(0 <= score <= 1 for score in exported)
    assert Path(manifest["model_uri"]).joinpath("MLmodel").is_file()
    assert report["selected_model"] == "logistic"
    fitted = registry.unwrap_python_model().pipeline
    training, _, _ = chronological_split(frame, config["time_column"])
    np.testing.assert_allclose(
        fitted.named_steps["scale"].mean_, training[config["features"]].mean().to_numpy()
    )
    run = mlflow.MlflowClient().get_run(report["run_id"])
    assert run.info.status == "FINISHED"
    assert run.data.params["dataset_sha256"] == report["dataset_sha256"]


def test_failed_acceptance_does_not_register_or_publish_model(synthetic_training):
    config, _, output = synthetic_training
    config["minimum_accuracy"] = 1.0  # The gate requires accuracy strictly greater than this.
    with pytest.raises(RuntimeError, match="Acceptance criteria failed"):
        train(config, output)
    assert not (output / "manifest.json").exists()
    assert mlflow.MlflowClient().search_registered_models() == []
    report_file = next((output / "training").glob("*/report.json"))
    report = json.loads(report_file.read_text())
    assert report["acceptance_passed"] is False
    assert mlflow.MlflowClient().get_run(report["run_id"]).info.status == "FAILED"
