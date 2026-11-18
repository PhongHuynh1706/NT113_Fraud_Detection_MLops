"""Render a deployment without applying it. Inputs come from the environment."""

import hashlib
import json
import os
import re
import subprocess
import sys

import yaml

from fraud_detection.model import ModelManifest


def render(environment: str) -> str:
    if environment not in {"test", "production"}:
        raise ValueError("Environment must be test or production")
    image = os.environ["DEPLOY_IMAGE"]
    if not re.fullmatch(r"ghcr\.io/[a-z0-9_./-]+@sha256:[a-f0-9]{64}", image):
        raise ValueError("An immutable GHCR image digest is required")
    manifest = ModelManifest.model_validate_json(os.environ["MODEL_MANIFEST_JSON"])
    # Registry aliases are mutable; deploy an explicit registered version instead.
    match = re.fullmatch(r"models:/[^/@]+/([1-9][0-9]*)", manifest.model_uri)
    if match is None or manifest.model_version != match.group(1):
        raise ValueError("Deployment requires matching numeric MLflow registry URI and version")
    host = os.environ["INGRESS_HOST"]
    ingress_class = os.environ["INGRESS_CLASS"]
    tracking_uri = os.environ["MLFLOW_TRACKING_URI"]
    if not host or host.endswith(".invalid") or not ingress_class or not tracking_uri:
        raise ValueError("Configure ingress host, class and MLflow tracking URI")
    tls_secret = os.environ.get("INGRESS_TLS_SECRET", "")
    if environment == "production" and not tls_secret:
        raise ValueError("Production requires an existing ingress TLS secret")
    completed = subprocess.run(
        ["kubectl", "kustomize", f"K8s/overlays/{environment}"],
        check=True,
        capture_output=True,
        text=True,
    )
    documents = list(yaml.safe_load_all(completed.stdout))
    serialized = manifest.model_dump_json()
    manifest_name = "fraud-model-" + hashlib.sha256(serialized.encode()).hexdigest()[:12]
    namespace = f"fraud-{environment}"
    for document in documents:
        kind = document["kind"]
        if kind == "ConfigMap":
            old_name = document["metadata"]["name"]
            new_name = "fraud-runtime-" + hashlib.sha256(tracking_uri.encode()).hexdigest()[:12]
            document["metadata"]["name"] = new_name
            document["data"]["MLFLOW_TRACKING_URI"] = tracking_uri
            for candidate in documents:
                if candidate["kind"] == "Deployment":
                    env_from = candidate["spec"]["template"]["spec"]["containers"][0]["envFrom"]
                    for source in env_from:
                        if source.get("configMapRef", {}).get("name") == old_name:
                            source["configMapRef"]["name"] = new_name
        elif kind == "Deployment":
            pod = document["spec"]["template"]["spec"]
            pod["containers"][0]["image"] = image
            pod["volumes"][0]["configMap"]["name"] = manifest_name
            if pull_secret := os.environ.get("IMAGE_PULL_SECRET"):
                pod["imagePullSecrets"] = [{"name": pull_secret}]
        elif kind == "Ingress":
            document["spec"]["rules"][0]["host"] = host
            document["spec"]["ingressClassName"] = ingress_class
            if tls_secret:
                document["spec"]["tls"] = [{"hosts": [host], "secretName": tls_secret}]
    documents.insert(
        0,
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": manifest_name, "namespace": namespace},
            "immutable": True,
            "data": {"manifest.json": serialized},
        },
    )
    return yaml.safe_dump_all(documents, sort_keys=False)


if __name__ == "__main__":
    try:
        print(render(sys.argv[1]))
    except (ValueError, KeyError, subprocess.CalledProcessError, json.JSONDecodeError):
        sys.exit("Deployment rendering failed: check required environment configuration")
