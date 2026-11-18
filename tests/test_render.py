import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

spec = importlib.util.spec_from_file_location("renderer", Path("workflow/render.py"))
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


@pytest.fixture
def deploy_env(monkeypatch):
    values = {
        "DEPLOY_IMAGE": "ghcr.io/example/fraud@sha256:" + "a" * 64,
        "MODEL_MANIFEST_JSON": '{"model_uri":"models:/Fraud/1","model_version":"1",'
        '"features":["synthetic_a"],"threshold":0.6}',
        "INGRESS_HOST": "fraud.test.example.com",
        "INGRESS_CLASS": "nginx",
        "MLFLOW_TRACKING_URI": "https://mlflow.test.example.com",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("INGRESS_TLS_SECRET", raising=False)
    documents = [
        {"kind": "ConfigMap", "metadata": {"name": "old"}, "data": {}},
        {
            "kind": "Deployment",
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {"image": "old", "envFrom": [{"configMapRef": {"name": "old"}}]}
                        ],
                        "volumes": [{"configMap": {"name": "old"}}],
                    }
                }
            },
        },
        {"kind": "Ingress", "spec": {"rules": [{"host": "old"}]}},
    ]
    monkeypatch.setattr(
        renderer.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout=yaml.safe_dump_all(documents)),
    )


def test_versioned_model_and_config_are_rendered(deploy_env):
    docs = list(yaml.safe_load_all(renderer.render("test")))
    model_cm, config, deployment, ingress = docs
    pod = deployment["spec"]["template"]["spec"]
    assert pod["volumes"][0]["configMap"]["name"] == model_cm["metadata"]["name"]
    assert pod["containers"][0]["envFrom"][0]["configMapRef"]["name"] == config["metadata"]["name"]
    assert "@sha256:" in pod["containers"][0]["image"]
    assert ingress["spec"]["ingressClassName"] == "nginx"


def test_production_requires_tls(deploy_env):
    with pytest.raises(ValueError, match="TLS"):
        renderer.render("production")


def test_mutable_image_rejected(deploy_env, monkeypatch):
    monkeypatch.setenv("DEPLOY_IMAGE", "ghcr.io/example/fraud:latest")
    with pytest.raises(ValueError, match="digest"):
        renderer.render("test")
