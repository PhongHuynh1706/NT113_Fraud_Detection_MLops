import json
import subprocess

import pytest

from workflow.build_model_image import build_model_image


@pytest.fixture
def registered(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    (model / "MLmodel").write_text("test fixture")
    (tmp_path / "manifest.local.json").write_text(
        json.dumps(
            {
                "model_uri": str(model),
                "model_version": "3",
                "features": ["x"],
                "threshold": 0.4,
            }
        )
    )
    return tmp_path, {
        "improved": True,
        "registered": True,
        "reload_verified": True,
        "model_version": "3",
        "run_id": "abc123",
    }


@pytest.mark.parametrize("missing", ["improved", "registered", "reload_verified"])
def test_gate_prevents_any_docker_call(registered, monkeypatch, missing):
    root, report = registered
    report[missing] = False

    def forbidden(*args, **kwargs):
        pytest.fail("Docker must not run when gate fails")

    monkeypatch.setattr(subprocess, "run", forbidden)
    assert build_model_image(root, report)["status"] == "skipped"


def test_bundles_exact_model_and_records_image(registered, monkeypatch):
    root, report = registered
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[1] == "build" and command[-1] != ".":
            context = root / "image-context"
            assert (context / "model/MLmodel").read_text() == "test fixture"
            manifest = json.loads((context / "manifest.json").read_text())
            assert manifest["model_uri"] == "/opt/fraud/model"
            assert manifest["model_version"] == "3"
        return subprocess.CompletedProcess(command, 0, stdout="sha256:abc\n")

    monkeypatch.setattr(subprocess, "run", run)
    result = build_model_image(root, report)
    assert result["status"] == "built"
    assert result["tag"] == "fraud-api:v3-abc123"
    assert result["image_id"] == "sha256:abc"
    assert len(calls) == 3
    assert not (root / "image-context").exists()
    assert (root / "model/MLmodel").exists()


def test_failed_build_propagates_and_keeps_model(registered, monkeypatch):
    root, report = registered

    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        build_model_image(root, report)
    assert not (root / "image-context").exists()
    assert (root / "docker-build.log").exists()
    assert not (root / "image.json").exists()
    assert (root / "model/MLmodel").exists()


def test_version_mismatch_rejected(registered):
    root, report = registered
    report["model_version"] = "4"
    with pytest.raises(ValueError, match="versions differ"):
        build_model_image(root, report)
