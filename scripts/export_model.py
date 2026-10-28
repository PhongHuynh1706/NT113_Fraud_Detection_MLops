
import json
import os
import shutil
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient


TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    "http://127.0.0.1:5000",
)

MODEL_NAME = os.getenv(
    "MODEL_NAME",
    "fraud-detection-model",
)

MODEL_ALIAS = os.getenv(
    "MODEL_ALIAS",
    "candidate",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "model"


def main():
    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_registry_uri(TRACKING_URI)

    client = MlflowClient()

    # Lấy model version từ alias
    version_info = client.get_model_version_by_alias(
        MODEL_NAME,
        MODEL_ALIAS,
    )

    version = str(version_info.version)
    model_uri = f"models:/{MODEL_NAME}/{version}"

    run_id = version_info.run_id

    if not run_id:
        run_id = mlflow.models.get_model_info(
            model_uri
        ).run_id

    if not run_id:
        raise RuntimeError(
            "Cannot determine training run ID"
        )

    print(f"Exporting {MODEL_NAME} v{version}")

    # Download model vào thư mục tạm
    downloaded_model = Path(
        mlflow.artifacts.download_artifacts(
            artifact_uri=model_uri,
        )
    )

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    shutil.copytree(
        downloaded_model,
        OUTPUT_DIR,
    )

    # Download preprocessing và threshold
    config_dir = OUTPUT_DIR / "inference_config"
    config_dir.mkdir(parents=True, exist_ok=True)

    for filename in (
        "preprocessing.json",
        "threshold.json",
    ):
        artifact_path = (
            f"inference_config/{filename}"
        )

        downloaded_file = client.download_artifacts(
            run_id,
            artifact_path,
        )

        shutil.copy2(
            downloaded_file,
            config_dir / filename,
        )

    # Tạo metadata cho Docker serving
    metadata = {
        "model_name": MODEL_NAME,
        "model_version": version,
        "run_id": run_id,
    }

    with (
        OUTPUT_DIR / "model_metadata.json"
    ).open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"Export completed: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
