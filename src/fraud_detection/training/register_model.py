
import argparse
import os

import mlflow
import yaml
from mlflow.tracking import MlflowClient


def register_model(config_path, model_uri, alias=None):
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    mlflow_config = config["mlflow"]

    tracking_uri = os.getenv(
        "MLFLOW_TRACKING_URI",
        mlflow_config["tracking_uri"],
    )

    registered_name = mlflow_config["registered_model_name"]
    alias = alias or mlflow_config.get(
        "candidate_alias", "candidate"
    )

    mlflow.set_tracking_uri(tracking_uri)

    client = MlflowClient()

    # Register logged model as a new model version
    model_version = mlflow.register_model(
        model_uri=model_uri,
        name=registered_name,
        await_registration_for=300,
    )

    # Attach alias to the newly registered version
    client.set_registered_model_alias(
        name=registered_name,
        alias=alias,
        version=model_version.version,
    )

    registered_uri = (
        f"models:/{registered_name}@{alias}"
    )

    print("\n=== MODEL REGISTERED ===")
    print(f"Name: {registered_name}")
    print(f"Version: {model_version.version}")
    print(f"Alias: {alias}")
    print(f"URI: {registered_uri}")

    return {
        "name": registered_name,
        "version": model_version.version,
        "alias": alias,
        "model_uri": registered_uri,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Register Fraud Detection Model"
    )

    parser.add_argument(
        "--config",
        default="configs/training.yml",
    )

    parser.add_argument(
        "--model-uri",
        required=True,
        help="MLflow logged model URI",
    )

    parser.add_argument(
        "--alias",
        default=None,
    )

    args = parser.parse_args()

    register_model(
        config_path=args.config,
        model_uri=args.model_uri,
        alias=args.alias,
    )
