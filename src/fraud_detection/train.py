"""Chronological training, validation-only selection, and one held-out evaluation."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from fraud_detection.model import ModelManifest, ModelRuntime
from fraud_detection.probability_model import FraudProbabilityModel

FORBIDDEN_FEATURES = {
    "is_fraud",
    "fraud_type",
    "fraud_amount_lost",
    "transaction_id",
    "customer_id",
    "card_id",
    "merchant_id",
    "transaction_datetime",
}


def chronological_split(frame, time_column, train_fraction=0.7, validation_fraction=0.15):
    if not 0 < train_fraction < train_fraction + validation_fraction < 1:
        raise ValueError("Invalid split fractions")
    timestamps = pd.to_datetime(frame[time_column], errors="raise", utc=True)
    if timestamps.isna().any():
        raise ValueError("Missing transaction timestamps")
    ordered_times = timestamps.sort_values()
    first = ordered_times.iloc[int(len(frame) * train_fraction)]
    second = ordered_times.iloc[int(len(frame) * (train_fraction + validation_fraction))]
    masks = (
        timestamps < first,
        (timestamps >= first) & (timestamps < second),
        timestamps >= second,
    )
    splits = tuple(frame.loc[mask].sort_values(time_column).copy() for mask in masks)
    if any(part.empty or part["is_fraud"].nunique() != 2 for part in splits):
        raise ValueError("Each chronological split needs both classes")
    return splits


def select_threshold(labels, probabilities):
    precision, recall, thresholds = precision_recall_curve(labels, probabilities)
    f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-15)
    return float(thresholds[int(np.argmax(f1))])


def evaluate(labels, probabilities, threshold):
    predicted = probabilities >= threshold
    return {
        "accuracy": float(accuracy_score(labels, predicted)),
        "precision": float(precision_score(labels, predicted, zero_division=0)),
        "recall": float(recall_score(labels, predicted, zero_division=0)),
        "f1": float(f1_score(labels, predicted, zero_division=0)),
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "confusion_matrix": confusion_matrix(labels, predicted, labels=[0, 1]).tolist(),
    }


def write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


def train(config, output_root=Path("artifacts"), tracking_uri=None):
    start = time.perf_counter()
    features = config["features"]
    if set(features) & (FORBIDDEN_FEATURES | {config["label"], config["time_column"]}):
        raise ValueError("Forbidden identifier, label or post-outcome feature")
    if len(features) != len(set(features)):
        raise ValueError("Duplicate feature names")
    dataset = Path(config["dataset"])
    frame = pd.read_csv(dataset)
    if config["label"] != "is_fraud" or set(frame[config["label"]].unique()) != {0, 1}:
        raise ValueError("Expected complete binary is_fraud labels")
    if frame["transaction_id"].duplicated().any():
        raise ValueError("Duplicate transaction IDs must be investigated before training")
    values = frame[features]
    if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in values.dtypes):
        raise ValueError("Current serving contract requires numeric features")
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError("Missing or nonfinite model input values")
    # Match the API's numeric serving contract and the MLflow double signature.
    frame[features] = frame[features].astype("float64")
    train_set, validation, test = chronological_split(
        frame, config["time_column"], config["train_fraction"], config["validation_fraction"]
    )
    x_train, y_train = train_set[features], train_set[config["label"]]
    x_val, y_val = validation[features], validation[config["label"]]
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    uri = tracking_uri or f"sqlite:///{(root / 'mlflow.db').as_posix()}"
    mlflow.set_tracking_uri(uri)
    mlflow.set_registry_uri(uri)
    client = mlflow.MlflowClient()
    experiment = client.get_experiment_by_name(config["experiment"])
    experiment_id = (
        experiment.experiment_id
        if experiment
        else client.create_experiment(
            config["experiment"], artifact_location=(root / "mlflow-artifacts").as_uri()
        )
    )
    candidates = {
        "logistic": Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        class_weight="balanced",
                        random_state=config["seed"],
                        **config["candidates"]["logistic"],
                    ),
                ),
            ]
        ),
        "hist_gradient_boosting": Pipeline(
            [
                (
                    "classifier",
                    HistGradientBoostingClassifier(
                        class_weight="balanced",
                        early_stopping=False,
                        random_state=config["seed"],
                        **config["candidates"]["hist_gradient_boosting"],
                    ),
                )
            ]
        ),
    }
    with mlflow.start_run(experiment_id=experiment_id, run_name="chronological-training") as run:
        folder = root / "training" / run.info.run_id
        folder.mkdir(parents=True)
        fingerprint = hashlib.sha256(dataset.read_bytes()).hexdigest()
        source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        commit = revision.stdout.strip() if revision.returncode == 0 else "uncommitted"
        versions = {
            name: importlib.metadata.version(name)
            for name in [
                "scikit-learn",
                "numpy",
                "pandas",
                "mlflow",
                "cloudpickle",
                "threadpoolctl",
            ]
        }
        mlflow.log_params(
            {
                "seed": config["seed"],
                "dataset_sha256": fingerprint,
                "split": "chronological_70_15_15",
                "threshold_objective": "validation_f1",
                "training_source_sha256": source_hash,
                "git_commit": commit,
                "max_threads": config["max_threads"],
                "feature_count": len(features),
            }
        )
        baseline = DummyClassifier(strategy="prior").fit(x_train, y_train)
        choices = {}
        with threadpool_limits(limits=config["max_threads"]):
            for name, pipeline in candidates.items():
                pipeline.fit(x_train, y_train)
                probability = pipeline.predict_proba(x_val)[:, list(pipeline.classes_).index(1)]
                threshold = select_threshold(y_val, probability)
                metrics = evaluate(y_val, probability, threshold)
                choices[name] = {"threshold": threshold, "validation": metrics}
                mlflow.log_metrics(
                    {
                        f"validation_{name}_{k}": v
                        for k, v in metrics.items()
                        if k != "confusion_matrix"
                    }
                )
                print(json.dumps({"candidate": name, **choices[name]}), flush=True)
            winner = max(
                choices,
                key=lambda name: (
                    choices[name]["validation"]["f1"],
                    choices[name]["validation"]["pr_auc"],
                ),
            )
            pipeline = candidates[winner]
            threshold = choices[winner]["threshold"]
            # No refit or tuning after this point: evaluate the held-out test once.
            test_probability = pipeline.predict_proba(test[features])[
                :, list(pipeline.classes_).index(1)
            ]
        test_metrics = evaluate(test[config["label"]], test_probability, threshold)
        baseline_probability = baseline.predict_proba(test[features])[
            :, list(baseline.classes_).index(1)
        ]
        baseline_metrics = evaluate(test[config["label"]], baseline_probability, 0.5)
        passed = (
            test_metrics["accuracy"] > config["minimum_accuracy"]
            and test_metrics["f1"] > baseline_metrics["f1"]
            and test_metrics["pr_auc"] > baseline_metrics["pr_auc"]
        )
        split_info = {}
        for name, part in zip(
            ["train", "validation", "test"], [train_set, validation, test], strict=True
        ):
            split_info[name] = {
                "rows": len(part),
                "fraud_count": int(part.is_fraud.sum()),
                "time_min": str(part[config["time_column"]].min()),
                "time_max": str(part[config["time_column"]].max()),
            }
        report = {
            "run_id": run.info.run_id,
            "tracking_uri": uri,
            "dataset_sha256": fingerprint,
            "dataset_rows": len(frame),
            "fraud_count": int(frame.is_fraud.sum()),
            "features": features,
            "excluded_columns": [c for c in frame if c not in features],
            "missing_by_column": frame.isna().sum().astype(int).to_dict(),
            "splits": split_info,
            "candidates": choices,
            "selected_model": winner,
            "threshold": threshold,
            "test": test_metrics,
            "baseline_test": baseline_metrics,
            "acceptance_passed": passed,
            "versions": versions,
            "git_commit": commit,
            "customer_overlap_train_test": len(set(train_set.customer_id) & set(test.customer_id)),
            "limitations": [
                "Dataset provenance/label maturity unverified; some timestamps are in the future.",
                "Repeated-customer chronological evaluation, not an unseen-customer benchmark.",
                "Historical aggregates excluded until point-in-time construction is verified.",
                "Threshold maximizes validation F1; business cost/alert budget unspecified.",
                "Precomputed flags/distance need provenance checks before production.",
                "No production readiness claim; no production model alias is updated.",
            ],
        }
        mlflow.log_params({"selected_model": winner, "threshold": threshold})
        mlflow.log_metrics(
            {f"test_{k}": v for k, v in test_metrics.items() if k != "confusion_matrix"}
        )
        mlflow.log_metrics(
            {
                f"baseline_test_{k}": v
                for k, v in baseline_metrics.items()
                if k != "confusion_matrix"
            }
        )
        mlflow.set_tag("acceptance_passed", str(passed).lower())
        write_json(folder / "config.json", config)
        write_json(folder / "dependencies.json", versions)
        write_json(folder / "report.json", report)
        # Source is retained because this repository may not yet have a commit.
        mlflow.log_artifact(str(Path(__file__)), artifact_path="source")
        mlflow.log_artifact(
            str(Path(__file__).with_name("probability_model.py")), artifact_path="source"
        )
        if not passed:
            write_json(folder / "report.json", report)
            mlflow.log_artifacts(str(folder), artifact_path="evaluation")
            raise RuntimeError("Acceptance criteria failed; model was not registered")
        wrapped = FraudProbabilityModel(pipeline)
        # A zero-valued synthetic example avoids logging raw transaction payloads.
        example = pd.DataFrame([{feature: 0.0 for feature in features}])
        requirements = [f"{name}=={version}" for name, version in versions.items()]
        info = mlflow.pyfunc.log_model(
            name="fraud-probability",
            python_model=wrapped,
            code_paths=[str(Path(__file__).parent)],
            signature=infer_signature(example, wrapped.predict(None, example)),
            input_example=example,
            pip_requirements=requirements,
        )
        reloaded = mlflow.pyfunc.load_model(info.model_uri)
        check = test[features].iloc[:128]
        np.testing.assert_allclose(
            reloaded.predict(check)["fraud_probability"],
            wrapped.predict(None, check)["fraud_probability"],
            rtol=1e-12,
        )
        version = mlflow.register_model(info.model_uri, config["registered_model"])
        manifest = ModelManifest(
            model_uri=f"models:/{config['registered_model']}/{version.version}",
            model_version=str(version.version),
            features=features,
            threshold=threshold,
        )
        write_json(folder / "manifest.json", manifest.model_dump())
        runtime = ModelRuntime.load(str(folder / "manifest.json"))
        np.testing.assert_allclose(
            runtime.predict(check.to_dict(orient="records")),
            wrapped.predict(None, check)["fraud_probability"],
            rtol=1e-12,
        )
        # Export a self-contained local MLflow model for serving without the registry.
        local_model = folder / "model"
        downloaded = mlflow.artifacts.download_artifacts(artifact_uri=info.model_uri)
        shutil.copytree(downloaded, local_model)
        local_manifest = manifest.model_copy(update={"model_uri": str(local_model)})
        write_json(folder / "manifest.local.json", local_manifest.model_dump())
        report.update(
            {
                "model_uri": manifest.model_uri,
                "model_version": str(version.version),
                "reload_verified": True,
                "duration_seconds": time.perf_counter() - start,
            }
        )
        write_json(folder / "report.json", report)
        for metadata_file in folder.glob("*.json"):
            mlflow.log_artifact(str(metadata_file), artifact_path="evaluation")
        write_json(root / "manifest.json", local_manifest.model_dump())
        write_json(root / "manifest.registry.json", manifest.model_dump())
        print(
            json.dumps(
                {
                    "output": str(folder),
                    "model_uri": manifest.model_uri,
                    "test": test_metrics,
                    "baseline": baseline_metrics,
                }
            ),
            flush=True,
        )
        return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/training.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    parser.add_argument("--tracking-uri", default=os.getenv("MLFLOW_TRACKING_URI"))
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    train(config, args.output, args.tracking_uri)


if __name__ == "__main__":
    main()
