"""Copy existing local model versions to the Docker MLflow server without retraining."""

import json
from pathlib import Path

import mlflow
from mlflow.entities import Metric, Param, RunTag
from mlflow.exceptions import MlflowException


def main():
    source_uri = "sqlite:///D:/MLops_Fraud_Detection/artifacts/mlflow.db"
    target_uri = "http://127.0.0.1:5000"
    source = mlflow.MlflowClient(tracking_uri=source_uri, registry_uri=source_uri)
    target = mlflow.MlflowClient(tracking_uri=target_uri, registry_uri=target_uri)
    name = "FraudDetection"
    versions = sorted(source.search_model_versions(f"name='{name}'"), key=lambda v: int(v.version))
    mapping = []
    try:
        target.get_registered_model(name)
    except MlflowException as error:
        if error.error_code != "RESOURCE_DOES_NOT_EXIST":
            raise
        target.create_registered_model(name)
    for version in versions:
        existing = [
            v
            for v in target.search_model_versions(f"name='{name}'")
            if str(v.version) == str(version.version)
        ]
        if existing:
            if existing[0].tags.get("origin_run_id") != version.run_id:
                raise ValueError(
                    "Target version already exists with a different origin; refusing overwrite"
                )
            mapping.append(
                {
                    "version": str(version.version),
                    "origin_run_id": version.run_id,
                    "server_run_id": existing[0].run_id,
                }
            )
            continue
        run = source.get_run(version.run_id)
        experiment_name = source.get_experiment(run.info.experiment_id).name
        experiment = target.get_experiment_by_name(experiment_name)
        experiment_id = (
            experiment.experiment_id if experiment else target.create_experiment(experiment_name)
        )
        copied = target.create_run(
            experiment_id,
            start_time=run.info.start_time,
            tags={
                "mlflow.runName": f"imported-v{version.version}",
                "origin_run_id": version.run_id,
                "origin_tracking_uri": source_uri,
                "copied_without_retraining": "true",
            },
        )
        destination_id = copied.info.run_id
        target.log_batch(
            destination_id,
            metrics=[
                Metric(k, v, run.info.end_time or run.info.start_time, 0)
                for k, v in run.data.metrics.items()
            ],
            params=[Param(k, v) for k, v in run.data.params.items()],
            tags=[RunTag(k, v) for k, v in run.data.tags.items() if not k.startswith("mlflow.")],
        )
        folder = Path("artifacts/training") / version.run_id
        if not (folder / "model/MLmodel").exists():
            raise ValueError(f"Local exported model missing: {folder}")
        target.log_artifacts(destination_id, str(folder))
        new_version = target.create_model_version(
            name,
            f"runs:/{destination_id}/model",
            run_id=destination_id,
            description=version.description,
            tags={
                **version.tags,
                "origin_run_id": version.run_id,
                "origin_tracking_uri": source_uri,
            },
        )
        if str(new_version.version) != str(version.version):
            raise ValueError("Unexpected version allocation; stop rather than overwrite")
        target.set_terminated(destination_id, status=run.info.status, end_time=run.info.end_time)
        mapping.append(
            {
                "version": str(version.version),
                "origin_run_id": version.run_id,
                "server_run_id": destination_id,
            }
        )
    output = Path("artifacts/mlflow-server-sync.json")
    output.write_text(
        json.dumps(
            {"source": source_uri, "target": target_uri, "model": name, "versions": mapping},
            indent=2,
        )
    )
    print(output.read_text())


if __name__ == "__main__":
    main()
