"""Compare bounded validation trials; test one locked winner; register only if improved."""

import argparse
import hashlib
import importlib.metadata
import json
import shutil
from pathlib import Path

import joblib
import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.pipeline import Pipeline
from threadpoolctl import threadpool_limits

from fraud_detection.model import ModelManifest, ModelRuntime
from fraud_detection.probability_model import FraudProbabilityModel
from fraud_detection.selection import improves_reference
from fraud_detection.train import chronological_split, evaluate, select_threshold, write_json
from workflow.build_model_image import build_model_image


def main(search_path="configs/improvement.json"):
    search = json.loads(Path(search_path).read_text())
    config = json.loads(Path(search["base_config"]).read_text())
    mlflow.set_tracking_uri(search["tracking_uri"])
    mlflow.set_registry_uri(search["tracking_uri"])
    mlflow.set_experiment(search["experiment"])
    client = mlflow.MlflowClient()
    reference_version = client.get_model_version(
        config["registered_model"], search["reference_version"]
    )
    reference_run = client.get_run(reference_version.run_id)
    reference = {
        k: reference_run.data.metrics[f"test_{k}"]
        for k in ["accuracy", "precision", "recall", "f1", "pr_auc", "roc_auc"]
    }
    fingerprint = hashlib.sha256(Path(config["dataset"]).read_bytes()).hexdigest()
    if reference_run.data.params["dataset_sha256"] != fingerprint:
        raise ValueError("Dataset differs from reference version; cannot compare this holdout")
    frame = pd.read_csv(config["dataset"])
    features = config["features"]
    if not np.isfinite(frame.to_numpy()).all() or set(frame.Class.unique()) != {0, 1}:
        raise ValueError("Invalid ULB data")
    frame = frame.sort_values("Time").drop_duplicates(features).copy()
    frame[features] = frame[features].astype("float64")
    train, validation, test = chronological_split(
        frame, "Time", config["train_fraction"], config["validation_fraction"], "Class"
    )
    versions = {
        p: importlib.metadata.version(p)
        for p in [
            "scikit-learn",
            "mlflow",
            "pandas",
            "numpy",
            "cloudpickle",
            "threadpoolctl",
            "joblib",
        ]
    }
    with mlflow.start_run(run_name="validation-comparison") as parent:
        mlflow.log_params(
            {"dataset_sha256": fingerprint, "reference_version": search["reference_version"]}
        )
        root = Path("artifacts/improvements") / parent.info.run_id
        root.mkdir(parents=True)
        choices = []
        with threadpool_limits(limits=config["max_threads"]):
            for index, trial in enumerate(search["trials"], start=1):
                with mlflow.start_run(run_name=f"extra-trees-trial-{index}", nested=True) as run:
                    params = {**config["candidates"]["extra_trees"], **trial}
                    seed = params.pop("seed")
                    pipeline = Pipeline(
                        [
                            (
                                "classifier",
                                ExtraTreesClassifier(
                                    **params,
                                    random_state=seed,
                                    n_jobs=config["max_threads"],
                                ),
                            )
                        ]
                    )
                    pipeline.fit(train[features], train.Class)
                    scores = pipeline.predict_proba(validation[features])[:, 1]
                    threshold = select_threshold(
                        validation.Class,
                        scores,
                        config["threshold_minimum_recall"],
                        config["precision_target_exclusive"],
                        config["minimum_validation_alerts"],
                    )
                    feasible = threshold is not None
                    if threshold is None:
                        threshold = select_threshold(validation.Class, scores)
                    metrics = evaluate(validation.Class, scores, threshold)
                    result = {
                        "trial": index,
                        "run_id": run.info.run_id,
                        "params": params,
                        "seed": seed,
                        "threshold": threshold,
                        "feasible": feasible,
                        "validation": metrics,
                    }
                    folder = root / run.info.run_id
                    folder.mkdir()
                    joblib.dump(pipeline, folder / "pipeline.joblib")
                    write_json(folder / "validation.json", result)
                    mlflow.log_params(
                        {
                            **params,
                            "seed": seed,
                            "threshold": threshold,
                            "dataset_sha256": fingerprint,
                            "test_evaluated": False,
                        }
                    )
                    mlflow.log_metrics(
                        {
                            f"validation_{k}": v
                            for k, v in metrics.items()
                            if k != "confusion_matrix"
                        }
                    )
                    mlflow.log_dict(result, "validation.json")
                    choices.append(result)
                    write_json(root / "trials.json", choices)
                    print(json.dumps(result), flush=True)
        eligible = [item for item in choices if item["feasible"]]
        report = {
            "run_id": parent.info.run_id,
            "reference_version": search["reference_version"],
            "reference_test": reference,
            "trials": choices,
            "holdout_status": "Previously evaluated holdout; not fresh independent validation",
            "registered": False,
        }
        if eligible:
            winner = max(
                eligible, key=lambda item: (item["validation"]["f1"], item["validation"]["pr_auc"])
            )
            pipeline = joblib.load(root / winner["run_id"] / "pipeline.joblib")
            with threadpool_limits(limits=config["max_threads"]):
                scores = pipeline.predict_proba(test[features])[:, 1]
            metrics = evaluate(test.Class, scores, winner["threshold"])
            better = improves_reference(metrics, reference)
            report.update(
                selected_trial=winner["trial"],
                selected_run=winner["run_id"],
                threshold=winner["threshold"],
                test=metrics,
                improved=better,
            )
            mlflow.log_metrics(
                {f"test_{k}": v for k, v in metrics.items() if k != "confusion_matrix"}
            )
            if better:
                wrapped = FraudProbabilityModel(pipeline)
                example = pd.DataFrame([{feature: 0.0 for feature in features}])
                info = mlflow.pyfunc.log_model(
                    name="improved-model",
                    python_model=wrapped,
                    code_paths=["src/fraud_detection"],
                    input_example=example,
                    signature=infer_signature(example, wrapped.predict(None, example)),
                    pip_requirements=[f"{p}=={v}" for p, v in versions.items()],
                )
                restored = mlflow.pyfunc.load_model(info.model_uri)
                np.testing.assert_allclose(
                    restored.predict(test[features].iloc[:128])["fraud_probability"],
                    scores[:128],
                    rtol=1e-12,
                )
                version = mlflow.register_model(info.model_uri, config["registered_model"])
                registry = ModelManifest(
                    model_uri=f"models:/{config['registered_model']}/{version.version}",
                    model_version=str(version.version),
                    features=features,
                    threshold=winner["threshold"],
                )
                downloaded = mlflow.artifacts.download_artifacts(
                    info.model_uri, dst_path=str(root.resolve())
                )
                model_path = root / "model"
                shutil.copytree(downloaded, model_path)
                local = registry.model_copy(update={"model_uri": str(model_path.resolve())})
                write_json(root / "manifest.local.json", local.model_dump())
                runtime = ModelRuntime.load(str(root / "manifest.local.json"))
                np.testing.assert_allclose(
                    runtime.predict(test[features].iloc[:128].to_dict("records")),
                    scores[:128],
                    rtol=1e-12,
                )
                write_json(root / "manifest.registry.json", registry.model_dump())
                report.update(
                    registered=True,
                    model_uri=registry.model_uri,
                    model_version=str(version.version),
                    reload_verified=True,
                )
        # Persist registration before Docker: a failed build must remain traceable.
        write_json(root / "report.json", report)
        try:
            report["image"] = build_model_image(root, report)
        except Exception as error:
            report["image"] = {"status": "failed", "error_type": type(error).__name__}
            write_json(root / "report.json", report)
            mlflow.log_dict(report, "report.json")
            if (root / "docker-build.log").exists():
                mlflow.log_artifact(str(root / "docker-build.log"))
            raise
        write_json(root / "report.json", report)
        if report["image"]["status"] == "built":
            mlflow.log_dict(report["image"], "image.json")
            mlflow.log_artifact(str(root / "docker-build.log"))
        mlflow.log_dict(config, "base_config.json")
        mlflow.log_dict(search, "search_config.json")
        mlflow.log_dict(versions, "dependencies.json")
        mlflow.log_dict(report, "report.json")
        mlflow.log_artifact(__file__, "source")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/improvement.json")
    main(parser.parse_args().config)
