"""Build a local image with the exact verified model; never publish or deploy."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from fraud_detection.model import ModelManifest


def build_model_image(root, report):
    root = Path(root).resolve()
    if not (report.get("improved") and report.get("registered") and report.get("reload_verified")):
        return {"status": "skipped", "reason": "Model improvement/registration/reload gate not met"}
    manifest = ModelManifest.model_validate_json((root / "manifest.local.json").read_text())
    if manifest.model_version != report["model_version"]:
        raise ValueError("Report and manifest model versions differ")
    model = Path(manifest.model_uri).resolve()
    if model != root / "model" or not (model / "MLmodel").is_file():
        raise ValueError("Expected verified local model inside this run")
    run_id = report["run_id"]
    version = manifest.model_version
    if not run_id.isalnum() or not version.isdigit():
        raise ValueError("Invalid image identity")
    tag = f"fraud-api:v{version}-{run_id}"
    base_tag = f"fraud-api:runtime-{run_id}"
    project = Path(__file__).resolve().parents[1]
    context = root / "image-context"
    context.mkdir(exist_ok=False)
    try:
        shutil.copytree(model, context / "model")
        bundled = manifest.model_copy(update={"model_uri": "/opt/fraud/model"})
        (context / "manifest.json").write_text(bundled.model_dump_json(), encoding="utf-8")
        (context / "Dockerfile").write_text(
            f"FROM {base_tag}\n"
            "USER root\n"
            "COPY --chown=10001:10001 model /opt/fraud/model\n"
            "COPY --chown=10001:10001 manifest.json /opt/fraud/manifest.json\n"
            "RUN chmod -R a+rX /opt/fraud\n"
            "ENV MODEL_MANIFEST=/opt/fraud/manifest.json\n"
            f'LABEL fraud.model.version="{version}" fraud.run.id="{run_id}"\n'
            "USER 10001:10001\n",
            encoding="utf-8",
        )
        log_path = root / "docker-build.log"
        with log_path.open("w", encoding="utf-8") as log:
            for command in [
                ["docker", "build", "-f", "docker/Dockerfile", "-t", base_tag, "."],
                ["docker", "build", "-t", tag, str(context)],
            ]:
                subprocess.run(
                    command, cwd=project, stdout=log, stderr=subprocess.STDOUT, check=True
                )
        image_id = subprocess.run(
            ["docker", "image", "inspect", "--format={{.Id}}", tag],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        result = {
            "status": "built",
            "tag": tag,
            "image_id": image_id,
            "model_version": version,
            "run_id": run_id,
            "published": False,
        }
        (root / "image.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        # Only remove the disposable context created above, never the exported model.
        shutil.rmtree(context)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    try:
        report["image"] = build_model_image(args.report.parent, report)
    except Exception as error:
        report["image"] = {"status": "failed", "error_type": type(error).__name__}
        raise
    finally:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["image"]))


if __name__ == "__main__":
    main()
